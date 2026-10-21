"""작업 종류 목록(D-085). 작업 추가에서 업종 → 업무분야 → 작업 순으로 고른다.

- 법령 업종(legal=True)의 업종·업무분야 이름은 건설산업기본법 시행령 [별표 1] 제2호(전문공사)
  원문 그대로다. 발췌: rules/sources/construction_industry_enforcement_mst287349.json.
  tests/app/core/test_work_kinds.py가 원문 표와 이름·순서를 대조한다. 시설물유지관리업은
  별표의 효력 규정(2023-12-31까지 유효)이 끝나 넣지 않았다.
- legal=False 묶음(전기·정보통신·소방, 공사관리)은 다른 법령이나 원청·감리 업무라
  공온이 붙인 이름이다.
- 작업 이름은 현장에서 부르는 말로 공온이 정한 것이며 법령 분류가 아니다(D-085).
  날씨 판정은 이름이 판정 공종(rules.WORK_TYPE_LABELS)과 같은 작업만 한다. 판정 공종 이름은
  기준 원문의 이름이고 기존 작업이 그 이름으로 저장돼 있어 바꾸지 않는다.
  판정 공종이 아닌 작업도 공통 기준(폭염)은 판정한다(D-027).
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkField:
    name: str  # 업무분야
    kinds: tuple[str, ...]  # 작업 이름


@dataclass(frozen=True, slots=True)
class WorkTrade:
    name: str  # 업종
    legal: bool  # 건설산업기본법 시행령 별표 1의 전문공사 업종인가
    fields: tuple[WorkField, ...]


def _one(trade: str, field: str, *kinds: str) -> WorkTrade:
    return WorkTrade(trade, True, (WorkField(field, kinds),))


_CRANE, _AERIAL = "이동식 크레인", "고소작업대"
_GAS, _HEATING = "가스 배관", "난방 배관"

# fmt: off
WORK_TRADES = (
    WorkTrade("지반조성ㆍ포장공사업", True, (
        WorkField("토공사", ("터파기", "흙막이 설치", "되메우기·성토")),
        WorkField("포장공사", ("아스팔트 포장", "콘크리트 포장")),
        WorkField("보링ㆍ그라우팅ㆍ파일공사", ("파일 항타", "보링·그라우팅")),
    )),
    _one("실내건축공사업", "실내건축공사", "내장 마감", "경량 칸막이 설치"),
    WorkTrade("금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업", True, (
        WorkField("금속구조물ㆍ창호ㆍ온실공사", ("창호 설치", "커튼월 설치", "난간 설치")),
        WorkField("지붕판금ㆍ건축물조립공사", ("지붕 판금", "샌드위치패널 설치")),
    )),
    WorkTrade("도장ㆍ습식ㆍ방수ㆍ석공사업", True, (
        WorkField("도장공사", ("도장·방수",)),
        WorkField("습식ㆍ방수공사", ("도장·방수", "미장", "타일", "조적")),
        WorkField("석공사", ("석재 시공",)),
    )),
    WorkTrade("조경식재ㆍ시설물공사업", True, (
        WorkField("조경식재공사", ("수목 식재", "잔디 식재")),
        WorkField("조경시설물설치공사", ("조경시설물 설치",)),
    )),
    _one("철근ㆍ콘크리트공사업", "철근ㆍ콘크리트공사",
         "먹매김", "벽체 철근 배근", "슬라브 철근 배근", "벽체 형틀 설치", "슬라브 형틀 설치",
         "탈형(형틀 해체)", "타설 전 청소", "콘크리트 타설"),
    _one("구조물해체ㆍ비계공사업", "구조물해체ㆍ비계공사",
         "철거", "비계 설치·해체", "갱폼 인양", _CRANE, _AERIAL),
    _one("상ㆍ하수도설비공사업", "상하수도설비공사", "상하수도 배관"),
    _one("철도ㆍ궤도공사업", "철도ㆍ궤도공사", "궤도 부설"),
    _one("철강구조물공사업", "철강구조물공사", "철골 작업", "볼트 본조임", _CRANE, _AERIAL),
    WorkTrade("수중ㆍ준설공사업", True, (
        WorkField("수중공사", ("수중 작업",)),
        WorkField("준설공사", ("준설",)),
    )),
    WorkTrade("승강기ㆍ삭도공사업", True, (
        WorkField("승강기설치공사", ("엘리베이터 설치",)),
        WorkField("삭도설치공사", ("삭도 설치",)),
    )),
    WorkTrade("기계설비ㆍ가스공사업", True, (
        WorkField("기계설비공사", ("설비 슬리브 설치", "설비 배관", "덕트 설치")),
        WorkField("가스시설공사(제1종)", (_GAS,)),
    )),
    WorkTrade("가스ㆍ난방공사업", True, (
        WorkField("가스시설공사(제2종)", (_GAS,)),
        WorkField("가스시설공사(제3종)", (_GAS,)),
        WorkField("난방공사(제1종)", (_HEATING,)),
        WorkField("난방공사(제2종)", (_HEATING,)),
        WorkField("난방공사(제3종)", (_HEATING,)),
    )),
    WorkTrade("전기·정보통신·소방", False, (
        WorkField("전기공사", ("전기 배관 매립", "전기 입선")),
        WorkField("정보통신공사", ("통신 배관·배선",)),
        WorkField("소방시설공사", ("소방 배관",)),
    )),
    WorkTrade("공사관리(원청·감리)", False, (
        WorkField("검측·시험", ("검측(감리 입회)", "현장 품질시험")),
        WorkField("현장 관리", ("양생", "자재 반입")),
    )),
)
# fmt: on

# 고를 수 있는 작업 이름 전체(처음 나온 순서, 중복 없음).
WORK_KIND_NAMES = tuple(
    dict.fromkeys(kind for trade in WORK_TRADES for field in trade.fields for kind in field.kinds)
)

# 업체가 맡는 업종으로 고를 수 있는 이름(D-088). 작업 고르기의 업종 칸과 같은 순서·글자.
WORK_TRADE_NAMES = tuple(trade.name for trade in WORK_TRADES)


def trade_key(name: str) -> str | None:
    """업종 이름 → 작업 고르기의 업종 칸 키(t0, t1…). 목록에 없으면 None."""
    return f"t{WORK_TRADE_NAMES.index(name)}" if name in WORK_TRADE_NAMES else None
