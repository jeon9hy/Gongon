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

SOURCES_DIR = REPO_ROOT / "rules" / "sources"

# 기준표가 아직 없는 공종에 대해 받아 둔 KCS 원문(후보). 기준표를 만들면 이 연결은 필요 없어진다.
CANDIDATE_CODES = {
    "콘크리트 타설": ("KCS 14 20 40",),
    "도장·방수": ("KCS 41 47 00", "KCS 41 40 01", "KCS 41 40 06"),
    "아스팔트 포장": ("KCS 44 50 10",),
}
# 기준을 구해도 예보로 판정하기 어려운 공종과 그 이유(D-032와 같은 문제)
FORECAST_LIMITS = {
    "이동식 크레인": "장비 풍속 제한은 보통 순간풍속인데 단기예보에는 평균풍속만 있어요. "
    "현장 풍속 입력이 있어야 판정이 의미 있어요.",
    "고소작업대": "이동식 크레인과 같아요(순간풍속).",
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
    kma_via = "기상청 API허브" if settings.kma_apihub_key else "공공데이터포털"
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
    settings = get_settings()
    return (
        DataFeed("기상특보(강풍·호우·폭염·대설)", "기상청 · 공공데이터포털", "API",
                 "판정 근거에 특보 표시", "미연결", False),
        DataFeed("초단기예보·초단기실황", "기상청 · 공공데이터포털", "API",
                 "오늘 6시간 안 날씨", "미연결", False),
        DataFeed("지상관측(ASOS·AWS)", "기상청 API허브", "API",
                 "예보와 실제 관측 비교(C08)",
                 "미연결" + ("" if settings.kma_apihub_key else " · 키 없음"), False),
        DataFeed("공휴일(특일 정보)", "한국천문연구원 · 공공데이터포털", "API",
                 "달력·작업일", "미연결", False),
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


def _method_of(source: str) -> str:
    if "규칙" in source:
        return "법령 API 발췌"
    return "공식 PDF 발췌" if "KCS" in source else "-"


def _bases() -> tuple[BasisRow, ...]:
    rule_sets = rule_sets_by_label()
    rows = []
    for label in (*WORK_TYPE_LABELS, *COMMON_LABELS):
        status = basis_status(label)
        rule_set = rule_sets.get(label)
        candidates = CANDIDATE_CODES.get(label, ())
        note = FORECAST_LIMITS.get(label, "")
        if candidates:
            prefix = (
                "받아 둔 원문(기준표 반영 전): " if rule_set is None else "추가로 받아 둔 원문: "
            )
            note = prefix + ", ".join(candidates)
        if rule_set is None:
            rows.append(BasisRow(label, "기준 미확보", "unknown", "-",
                                 "KCSC API로 원문 받음" if candidates else "-", note))  # fmt: skip
            continue
        tone = "go" if rule_set.source_verified else "check"
        method = _method_of(rule_set.source)
        rows.append(BasisRow(label, status.replace("판정 · ", ""), tone, rule_set.source,
                             method, note))  # fmt: skip
    return tuple(rows)


def build_sources_view() -> SourcesView:
    files = tuple(_source_file(path) for path in sorted(SOURCES_DIR.glob("*.json")))
    return SourcesView(feeds=_feeds(), bases=_bases(), files=files, not_yet=_not_yet())
