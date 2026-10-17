"""판정 화면이 쓰는 표시용 모델. 판정 계산은 engine/judgment가 하고, 여기서는 보여줄 값만 담는다."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from engine.judgment.index import GongonIndex

VerdictFilter = Literal["전체", "진행", "확인 필요", "중지 검토", "판정 불가"]
ElementKey = Literal["rain", "wind", "snow", "heat"]
RunResult = Literal[
    "done",
    "failed",
    "no_rules",
    "all_done",
    "no_sites",
    "out_of_period",
    "beyond_forecast",
    "unchanged",
    "no_work",
]


@dataclass(frozen=True, slots=True)
class SiteOption:
    site_id: int
    name: str
    selected: bool


@dataclass(frozen=True, slots=True)
class WorkCard:
    """공종 하나의 내일 판정 요약. 기준이 없는 공종은 판정하지 않고 '확인 필요'로만 보인다."""

    work_type: str
    time_range: str
    verdict: str | None  # None: 아직 판정하지 않음
    reason: str
    detail_href: str | None
    open_href: str | None = None  # 대시보드에서 이 작업의 시간대별 예보 모달을 여는 주소


@dataclass(frozen=True, slots=True)
class WorkWindow:
    time_range: str
    verdict: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class Tile:
    verdict: str
    hours: int


@dataclass(frozen=True, slots=True)
class Bar:
    hour_label: str
    height_px: int
    tip: str
    aria_label: str
    over: bool
    selected: bool
    href: str


@dataclass(frozen=True, slots=True)
class Tab:
    label: str
    href: str
    selected: bool


@dataclass(frozen=True, slots=True)
class Chart:
    title: str
    tabs: tuple[Tab, ...]
    bars: tuple[Bar, ...]
    selected_value: str
    selected_caption: str
    threshold_bottom_px: int
    threshold_text: str


@dataclass(frozen=True, slots=True)
class NoticeItem:
    work: str
    verdict: str
    reason: str


@dataclass(frozen=True, slots=True)
class Notice:
    title: str
    items: tuple[NoticeItem, ...]
    detail_href: str | None


@dataclass(frozen=True, slots=True)
class PrimaryJudgment:
    """대시보드에서 시간대·그래프로 자세히 보여주는 판정(기준표가 있는 첫 공종)."""

    judgment_id: int
    work_type: str
    verdict: str
    windows: tuple[WorkWindow, ...]
    tiles: tuple[Tile, ...]
    chart: Chart | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class DashboardView:
    sites: tuple[SiteOption, ...]
    site_id: int | None  # None: 등록된 현장이 없음
    site_name: str
    target_date: str
    work_hours: str
    cards: tuple[WorkCard, ...]
    primary: PrimaryJudgment | None
    forecast_issued: str | None
    rule_version: str | None
    rule_verified: bool
    collection_status: str
    judged_at: str | None
    grid: str
    notice: Notice | None
    message: str | None
    message_is_error: bool
    off_period_note: str | None  # 대상 날짜가 작업 기간 밖이면 안내 문구
    week: "WeekView | None" = None  # 내일부터 7일(D-041)
    next_forecast: str = ""  # 다음 예보 발표·반영 시각 안내
    checked: str | None = None  # 마지막 판정 실행(확인) 시각(D-044)
    work_options: "tuple[WorkOption, ...]" = ()  # 상세 카드에서 고를 수 있는 작업(2개 이상일 때)
    detail_open: bool = False  # 작업·요소·시각을 골라 들어왔으면 시간대별 예보 모달을 바로 연다
    can_run: bool = True  # 7일 중 작업일이 있어 판정할 수 있는가


@dataclass(frozen=True, slots=True)
class CheckIssue:
    """공온 점검에서 걸린 항목 하나. key는 CHECK_LABELS의 키."""

    key: str
    label: str


@dataclass(frozen=True, slots=True)
class BoardItem:
    """오늘·내일 점검판의 작업 한 줄."""

    item_id: int
    site_name: str
    work_type: str
    time_text: str
    location: str
    company: str
    href: str  # 작업 일정의 그날
    issues: tuple[CheckIssue, ...]
    phase: Literal["before", "now", "done"] | None = None  # 오늘만
    phase_label: str = ""
    progress_pct: int = 0
    weather: str | None = None  # 내일만: 판정 4단계 이름, None은 판정 전


@dataclass(frozen=True, slots=True)
class DayBoard:
    key: Literal["today", "tomorrow"]
    title: str  # "오늘"·"내일"
    date_text: str
    items: tuple[BoardItem, ...]
    criteria: tuple[tuple[str, int], ...]  # (점검 항목 이름, 걸린 작업 수), 걸린 것만

    @property
    def ready(self) -> int:
        return sum(1 for i in self.items if not i.issues)


@dataclass(frozen=True, slots=True)
class HomeIndexDay:
    """홈의 이번 주 공온지수 한 칸. 현장이 여럿이면 그날 가장 낮은 점수를 보인다(가장 조심할 곳)."""

    label: str  # "10/17(토)"
    short: str  # "토 17" (좁은 화면)
    is_tomorrow: bool
    score: int | None  # None: 점수 없음(판정 전·중기 참고·작업 없음)
    sub: str  # 점수가 없을 때 이유, 있으면 현장 이름(여럿일 때)
    href: str


@dataclass(frozen=True, slots=True)
class HomeDay:
    date_text: str  # "10/18(일)" (읽기용 이름)
    short: str  # "일 18" (칸에 보이는 짧은 글)
    href: str
    works: int
    issues: int  # 점검에 걸린 작업 수(날씨는 내일만)
    is_today: bool
    is_weekend: bool


@dataclass(frozen=True, slots=True)
class SiteSummary:
    """홈의 현장 카드 한 장. 판정이 없으면 verdict는 None(판정 전)."""

    site_id: int
    name: str
    work_hours: str
    work_types: tuple[str, ...]
    verdict: str | None
    reason: str
    detail_href: str
    judged_at: str | None
    working: bool  # 대상 날짜가 작업 기간 안인가
    checked: str | None = None  # 마지막 판정 실행(확인) 시각·사용한 예보 발표(D-044)
    checked_short: str | None = None  # 홈 카드용 짧은 확인 시각('22:45 확인')
    cards: tuple[WorkCard, ...] = ()  # 작업·공종별 단계(작업 기간 밖이면 비어 있음)


@dataclass(frozen=True, slots=True)
class CountTile:
    label: str
    count: int
    badge: str | None  # 판정 4단계 이름이면 배지로 표시, None이면 '판정 전'


@dataclass(frozen=True, slots=True)
class SiteTab:
    """홈 위 현장 넘기기 칸(개발자 요청 2026-10-17). site_id None은 전체."""

    site_id: int | None
    name: str
    today_count: int
    selected: bool
    href: str


@dataclass(frozen=True, slots=True)
class HomeView:
    target_date: str
    today_date: str
    boards: tuple[DayBoard, ...]  # 오늘·내일 공온 점검판(D-065)
    week: tuple[HomeDay, ...]  # 오늘부터 7일
    index_days: tuple[HomeIndexDay, ...]  # 내일부터 7일 공온지수
    checked_short: str | None  # 가장 최근 점검(판정 실행) 시각 '15:15 확인'
    sites: tuple[SiteSummary, ...]
    tiles: tuple[CountTile, ...]
    forecast_status: str
    forecast_issued: str | None
    rule_version: str | None
    rule_verified: bool
    message: str | None
    message_is_error: bool
    next_forecast: str = ""
    tabs: tuple[SiteTab, ...] = ()  # 현장이 둘 이상일 때만
    selected_site_id: int | None = None  # 고른 현장(전체면 None). 메뉴 링크가 이어받는다


@dataclass(frozen=True, slots=True)
class CriterionCard:
    label: str
    icon: str
    verdict: str
    peak_value: str
    unit: str
    peak_time: str | None
    rule_text: str
    source: str
    source_verified: bool


@dataclass(frozen=True, slots=True)
class Cell:
    text: str
    over: bool


@dataclass(frozen=True, slots=True)
class HourRow:
    time: str
    cells: tuple[Cell, ...]
    verdict: str
    calculation: str


@dataclass(frozen=True, slots=True)
class DetailView:
    site_id: int | None
    site_name: str
    target_date: str
    work_type: str
    work_range: str
    verdict: str
    chips: tuple[str, ...]
    criteria: tuple[CriterionCard, ...]
    columns: tuple[str, ...]
    rows: tuple[HourRow, ...]
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class HistoryRow:
    judgment_id: int
    target_date: str
    site_name: str
    work_type: str
    time_range: str  # 작업 시간 구간(예: 07:00~17:00)
    verdict: str
    issued: str
    rule_version: str
    note: str | None


@dataclass(frozen=True, slots=True)
class HistorySite:
    """판정 내역의 한 날짜 안 한 현장 묶음."""

    site_name: str
    rows: tuple[HistoryRow, ...]


@dataclass(frozen=True, slots=True)
class HistoryDay:
    """판정 내역의 대상 날짜 묶음(최근 날짜부터)."""

    label: str  # "10월 13일(화)"
    count: int  # 이 쪽에 보이는 이 날짜의 판정 수
    sites: tuple[HistorySite, ...]


@dataclass(frozen=True, slots=True)
class FilterLink:
    label: str
    count: int
    href: str
    selected: bool


@dataclass(frozen=True, slots=True)
class PageLink:
    """쪽 번호 링크. href가 없으면 생략 표시('…')."""

    label: str
    href: str | None
    current: bool = False


@dataclass(frozen=True, slots=True)
class HistoryView:
    days: tuple[HistoryDay, ...]
    count: int  # 이 쪽에 보이는 판정 수
    total: int  # 조건에 맞는 전체 판정 수(작업별 최신)
    first_index: int  # 이 쪽 첫 판정의 순번(1부터, 없으면 0)
    size: int  # 한 쪽에 보이는 판정 수
    size_options: tuple[int, ...]
    pages: tuple[PageLink, ...]
    visible_rows: int  # 현장 묶음마다 바로 보이는 줄 수(나머지는 더보기)
    filters: tuple[FilterLink, ...]
    site_options: tuple[SiteOption, ...]
    selected_site_id: int | None
    selected_verdict: str
    page: int
    prev_href: str | None
    next_href: str | None


@dataclass(frozen=True, slots=True)
class WeekDay:
    """주간 보기 열 하나(D-041). confidence는 그날 판정에 쓴 예보 자료의 촘촘함(예보 상세도)이다."""

    day: date
    label: str  # 10/9(금)
    is_tomorrow: bool
    in_period: bool
    confidence: Literal[
        "높음", "보통", "낮음", "예보 없음", "판정 전", "수집 실패", "기간 밖", "작업 없음"
    ]
    confidence_note: str
    index: GongonIndex | None  # 공온지수(D-050). 판정이 없거나 중기예보 참고 날은 None
    index_note: str  # 공온지수 근거·예보 상세도 설명(마우스를 올리면 보임)


@dataclass(frozen=True, slots=True)
class WeekCell:
    verdict: str | None  # None: 그날 이 공종 판정 없음(state가 사유)
    state: Literal["verdict", "reference", "none", "pending", "off"]  # reference: 중기예보 참고
    href: str | None
    note: str


@dataclass(frozen=True, slots=True)
class WeekRow:
    work_type: str
    cells: tuple[WeekCell, ...]


@dataclass(frozen=True, slots=True)
class WeekView:
    days: tuple[WeekDay, ...]
    rows: tuple[WeekRow, ...]


@dataclass(frozen=True, slots=True)
class WorkOption:
    label: str
    verdict: str
    href: str
    selected: bool
