from dataclasses import dataclass
from typing import Literal

from app.features.changes.schemas import ChangeDetailView, RevisionView


@dataclass(frozen=True, slots=True)
class WeeklyWork:
    """주간 작업계획표 칸 안의 작업 한 건."""

    time_text: str
    work_type: str
    location: str
    verdict: str | None  # 판정 범위(내일부터 7일) 안의 날만. 범위 밖·판정 전이면 None
    issues: tuple[str, ...]  # 공온 점검과 같은 기준: 위치 없음·같은 곳 같은 시간·변경 검토 중


@dataclass(frozen=True, slots=True)
class WeeklyRow:
    company: str  # 업체 이름, 미지정이면 "실행 업체 미지정"
    cells: tuple[tuple[WeeklyWork, ...], ...]  # 월~일 7칸
    unassigned: bool = False


@dataclass(frozen=True, slots=True)
class WeeklyDay:
    iso: str
    text: str  # "11/2(월)"
    holiday: bool  # 토·일


@dataclass(frozen=True, slots=True)
class WeeklyAction:
    company: str
    title: str
    status_label: str
    due_text: str
    overdue: bool
    href: str


@dataclass(frozen=True, slots=True)
class WeeklyPlanView:
    site_id: int
    site_name: str
    period_text: str  # "11월 2일(월) ~ 11월 8일(일)"
    days: tuple[WeeklyDay, ...]
    rows: tuple[WeeklyRow, ...]
    work_count: int
    issue_count: int
    changes_period_text: str  # 확정 변경을 모은 기간
    changes: tuple[str, ...]
    actions: tuple[WeeklyAction, ...]
    prev_start: str
    next_start: str
    made_text: str  # "10/30(금) 14:05 · 김정현"


# 작업일보 결과(C14-2). 했음이 아니면 원인을 하나 이상 고른다(원인 코드는 변경 원인과 같다).
OUTCOME_LABELS: dict[str, str] = {"done": "했음", "partial": "일부만", "not_done": "못함"}
# 일부만·못함을 언제 알았나(D-113). 미리 알면 쉬고, 당일에 알면 반나절 인건비가 나간다.
KNOWN_LABELS: dict[str, str] = {
    "day_before": "전날",
    "morning": "당일 아침",
    "on_site": "현장 와서",
}
NOTE_MAX = 500
EQUIPMENT_MAX = 120
WORKERS_MAX = 999


@dataclass(frozen=True, slots=True)
class ReportForm:
    """화면 입력값 그대로(검증 실패 시 다시 보여 주려고 문자열로 둔다)."""

    outcome: str = ""
    causes: tuple[str, ...] = ()
    workers: str = ""
    equipment_note: str = ""
    note: str = ""
    known_when: str = ""


@dataclass(frozen=True, slots=True)
class ReportInput:
    outcome: str
    causes: tuple[str, ...]
    workers: int | None
    equipment_note: str
    note: str
    known_when: str | None = None


@dataclass(frozen=True, slots=True)
class DailyWork:
    item_id: int
    time_text: str
    work_type: str
    location: str
    outcome: str | None  # None은 미입력
    outcome_label: str
    causes_text: str
    known_text: str  # "당일 아침 알게 됨", 모르면 빈칸
    workers: int | None
    equipment_note: str
    note: str
    recorded_text: str  # "10/30 17:20 · 김정현"
    stale: bool  # 기록한 뒤 계획이 바뀌었다
    can_edit: bool
    form: ReportForm  # 고치기 폼의 지금 값
    change_href: str | None  # 계획과 달랐으면 변경 제안으로(제안할 수 있는 사람만)


@dataclass(frozen=True, slots=True)
class DailyRow:
    company: str
    works: tuple[DailyWork, ...]
    workers_total: int | None  # 인원이 하나도 없으면 None
    unassigned: bool = False


@dataclass(frozen=True, slots=True)
class DailyView:
    site_id: int
    site_name: str
    day_iso: str
    day_text: str  # "10월 30일(금)"
    recordable: bool  # 오늘까지만 기록한다
    rest_count: int  # 내가 기록할 수 있는데 아직 미입력인 작업('모두 했음' 대상)
    rows: tuple[DailyRow, ...]
    work_count: int
    recorded_count: int
    short_count: int  # 일부만·못함
    workers_total: int | None
    changes: tuple[str, ...]  # 그날 확정된 변경
    prev_day: str
    next_day: str
    made_text: str
    reason_labels: dict[str, str]
    outcome_labels: dict[str, str]
    known_labels: dict[str, str]
    errors: tuple[str, ...] = ()
    error_item_id: int | None = None


@dataclass(frozen=True, slots=True)
class WeatherEntry:
    company: str
    work_text: str  # "철골 작업 · 101동 · 07:30-09:30"
    outcome_label: str
    causes_text: str  # 기상 말고 함께 고른 원인까지
    known_text: str
    note: str
    verdict: str | None  # 작업 시작 전 마지막 판정. 없으면 None
    verdict_text: str  # "10/3 17:00 판정" 또는 "판정 기록 없음"


@dataclass(frozen=True, slots=True)
class WeatherDay:
    day_text: str
    entries: tuple[WeatherEntry, ...]
    all_stopped: bool  # 그날 작업이 모두 기상 원인으로 못함
    work_count: int  # 그날 작업 수


@dataclass(frozen=True, slots=True)
class WeatherLogView:
    site_id: int
    site_name: str
    month_text: str  # "2026년 10월"
    days: tuple[WeatherDay, ...]
    affected_days: int
    stopped_days: int  # 그날 작업이 모두 기상으로 못한 날
    not_done_count: int
    partial_count: int
    prev_month: str
    next_month: str
    made_text: str


ChangeDocKind = Literal["order", "report"]
CHANGE_DOC_TITLES: dict[str, str] = {"order": "변경 통보 · 작업 지시서", "report": "실정보고 초안"}


@dataclass(frozen=True, slots=True)
class ChangeDocView:
    """변경 건 문서(C14-4). 변경 건 상세 화면과 같은 값(changes 서비스)을 서류 모양으로 보인다."""

    kind: ChangeDocKind
    kind_title: str
    detail: ChangeDetailView
    current: RevisionView | None  # 현재 확정 버전, 없으면 가장 최근 버전
    confirmed: bool  # current가 확정 버전인가
    made_text: str


@dataclass(frozen=True, slots=True)
class LossRow:
    """원인 하나의 그달 차질(일부만·못함). 원인을 여러 개 고른 기록은 원인마다 센다."""

    label: str
    partial_count: int
    not_done_count: int
    workers_total: int | None  # 그 기록들에 적은 인원 합, 하나도 없으면 None
    known: tuple[int, ...]  # KNOWN_LABELS 순서의 건수 + 마지막은 모름


@dataclass(frozen=True, slots=True)
class LossSummaryView:
    site_id: int
    site_name: str
    month_text: str
    month_iso: str  # "2026-10"
    rows: tuple[LossRow, ...]  # 차질이 있는 원인만, 많은 순
    total: LossRow  # 기록 단위(중복 없이)
    known_headers: tuple[str, ...]
    recorded_count: int  # 그달 작업일보 전체
    prev_month: str
    next_month: str
    made_text: str
