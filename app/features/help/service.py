"""자료실(개발용, D-079): 판정에 쓰는 자료가 어디서 오는지 한 화면에 모은다.

기준표(rules/*.yaml)·발췌 파일(rules/sources/*.json)·설정 키를 그대로 읽어 보여 주므로,
기준을 추가하거나 원문을 다시 받으면 화면도 따라 바뀐다.
나중에 빼기 쉽게 이 파일과 화면 하나에만 둔다.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT, get_settings
from app.core.rules import COMMON_LABELS, WORK_TYPE_LABELS, basis_status, rule_sets_by_label
from engine.judgment.types import ELEMENT_LABEL

SOURCES_DIR = REPO_ROOT / "rules" / "sources"

# 예보(단기예보)로는 알 수 없어 판정하지 않는 것(D-080). 현장에서 확인한다.
NOT_JUDGED = {
    "철골 작업": "-",
    "콘크리트 타설": "타설·양생 중 콘크리트 온도, 초기동해 위험(현장 측정)",
    "이동식 크레인": "순간풍속·장비 허용풍속(설명서) — 예보는 평균풍속만 있음",
    "고소작업대": "순간풍속·장비 허용풍속(설명서) — 예보는 평균풍속만 있음",
    "도장·방수": "안개, 바탕 온도·이슬점, 바탕 동결·건조 상태",
    "아스팔트 포장": "안개, 포설면 동결·습윤 상태, 코우트 공정 10 ℃ 조건",
    "폭염(공통)": "현장 체감온도 측정·기록(제562조)",
}


@dataclass(frozen=True, slots=True)
class DataFeed:
    name: str
    provider: str
    method: str
    used_for: str
    status: str
    ok: bool


@dataclass(frozen=True, slots=True)
class BasisRow:
    label: str
    status: str
    tone: str  # go | check | unknown
    elements: str
    source: str
    method: str
    note: str


@dataclass(frozen=True, slots=True)
class SourceDoc:
    title: str
    excerpt_count: int


@dataclass(frozen=True, slots=True)
class SourceFile:
    file_name: str
    method: str
    retrieved_at: str
    documents: tuple[SourceDoc, ...]


@dataclass(frozen=True, slots=True)
class SourcesView:
    feeds: tuple[DataFeed, ...]
    bases: tuple[BasisRow, ...]
    files: tuple[SourceFile, ...]
    not_yet: tuple[DataFeed, ...]


def _feeds() -> tuple[DataFeed, ...]:
    settings = get_settings()
    kma = bool(settings.kma_apihub_key or settings.kma_service_key)
    # API허브 키가 있으면 먼저 쓰고, 실패하면 공공데이터포털로 받는다(engine/forecast/kma.py)
    kma_via = "API허브 → 실패 시 공공데이터포털" if settings.kma_apihub_key else "공공데이터포털"
    return (
        DataFeed("단기예보(시간별, 내일~3일)", f"기상청 · {kma_via}", "API",
                 "공온 판정·공온지수", "키 있음" if kma else "키 없음", kma),
        DataFeed("중기예보(4~7일)", "기상청 · 공공데이터포털", "API",
                 "공온지수 중기 참고(D-069)", "키 있음" if settings.kma_service_key else "키 없음",
                 bool(settings.kma_service_key)),
        DataFeed("체감온도 계산식", "기상청 기상자료개방포털", "문서 발췌(계산은 앱 안)",
                 "폭염 판정", "발췌 저장", True),
        DataFeed("주소 → 좌표", "카카오 로컬", "API", "현장 위치·기상청 격자",
                 "키 있음" if settings.kakao_rest_api_key else "키 없음(위경도 직접 입력)",
                 bool(settings.kakao_rest_api_key)),
        DataFeed("주소 찾기 창", "다음 우편번호", "웹 위젯", "현장 주소 입력",
                 "키 필요 없음", True),
    )  # fmt: skip


def _not_yet() -> tuple[DataFeed, ...]:
    # 활용신청 상태는 2026-10-17 실제 호출로 확인한 값이다(키가 바뀌면 다시 확인).
    return (
        DataFeed("기상특보(강풍·호우·폭염·대설)", "기상청 · 공공데이터포털", "API",
                 "판정 근거에 발효 중 특보 표시", "승인됨 · 코드 미연결", False),
        DataFeed("초단기실황·초단기예보", "기상청 · 공공데이터포털", "API",
                 "오늘 6시간 안 실제 날씨", "승인됨 · 코드 미연결", False),
        DataFeed("공휴일(특일 정보)", "한국천문연구원 · 공공데이터포털", "API",
                 "달력·작업일", "승인됨 · 코드 미연결", False),
        DataFeed("AWS 매분자료(순간풍속 포함)", "기상청 API허브", "API",
                 "실제 관측 바람·비, 예보 비교(C08)", "승인됨 · 코드 미연결", False),
        DataFeed("단기예보·ASOS 시간자료·특보", "기상청 API허브", "API",
                 "공공데이터포털과 같은 자료", "활용신청 안 됨(403)", False),
    )  # fmt: skip


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _source_file(path: Path) -> SourceFile:
    data = _load(path)
    if "law_name" in data:  # 국가법령정보센터 Open API 발췌
        parts = [*data.get("articles", {}), *data.get("appendices", {})]
        docs: tuple[SourceDoc, ...] = (
            SourceDoc(f"{data['law_name']} ({data.get('effective_on', '')} 시행)", len(parts)),
        )
        return SourceFile(
            path.name, "국가법령정보센터 Open API", data.get("retrieved_at", ""), docs
        )
    if "documents" in data:
        documents = data["documents"]
        by_api = any("kcsc.re.kr/OpenApi" in d.get("retrieved_from", "") for d in documents)
        docs = tuple(
            SourceDoc(
                d.get("title") or f"{d.get('code')} {d.get('name')} ({d.get('version')})",
                len(d.get("excerpts", {})),
            )
            for d in documents
        )
        method = "국가건설기준센터 OpenAPI" if by_api else "공식 PDF 직접 받음"
        when = data.get("retrieved_at") or data.get("retrieved_on", "")
        return SourceFile(path.name, method, when, docs)
    # 기상청 문서처럼 본문 한 건을 발췌한 파일
    doc = SourceDoc(f"{data.get('publisher', '')} · {data.get('document', '')}",
                    len(data.get("text", [])))  # fmt: skip
    return SourceFile(path.name, "웹 문서 발췌", data.get("retrieved_at", ""), (doc,))


def _methods_of(source: str) -> str:
    methods = []
    if "규칙" in source or "시행령" in source:
        methods.append("법령 API")
    if "KCS 14 20 40" in source or any(c in source for c in ("KCS 41", "KCS 44")):
        methods.append("KCSC API")
    if "가이드라인" in source or "KCS 14 20 41" in source:
        methods.append("공식 PDF")
    return " · ".join(methods) or "-"


def _bases() -> tuple[BasisRow, ...]:
    rule_sets = rule_sets_by_label()
    rows = []
    for label in (*WORK_TYPE_LABELS, *COMMON_LABELS):
        rule_set = rule_sets.get(label)
        note = NOT_JUDGED.get(label, "")
        if rule_set is None:
            rows.append(BasisRow(label, "기준 미확보", "unknown", "-", "-", "-", note))
            continue
        tone = "go" if rule_set.source_verified else "check"
        labels = dict.fromkeys(ELEMENT_LABEL[c.element] for c in rule_set.conditions)
        status = basis_status(label).replace("판정 · ", "")
        rows.append(BasisRow(label, status, tone, " · ".join(labels), rule_set.source,
                             _methods_of(rule_set.source), note))  # fmt: skip
    return tuple(rows)


def build_sources_view() -> SourcesView:
    files = tuple(_source_file(path) for path in sorted(SOURCES_DIR.glob("*.json")))
    return SourcesView(feeds=_feeds(), bases=_bases(), files=files, not_yet=_not_yet())
