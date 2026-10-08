"""판정 화면이 쓰는 표시용 모델. 판정 계산은 engine/judgment가 하고, 여기서는 보여줄 값만 담는다."""

from dataclasses import dataclass
from typing import Literal

VerdictFilter = Literal["전체", "진행", "확인 필요", "중지 검토", "판정 불가"]
ElementKey = Literal["rain", "wind", "snow", "heat"]
RunResult = Literal["done", "failed", "no_rules", "all_done", "no_sites", "out_of_period"]


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


@dataclass(frozen=True, slots=True)
class CountTile:
    label: str
    count: int
    badge: str | None  # 판정 4단계 이름이면 배지로 표시, None이면 '판정 전'


@dataclass(frozen=True, slots=True)
class RecentItem:
    work_type: str
    verdict: str
    href: str


@dataclass(frozen=True, slots=True)
class RecentRun:
    """홈의 최근 판정 한 줄: 한 현장을 한 번 판정한 결과(공종별 판정 묶음)."""

    site_name: str
    verdict: str  # 묶음 안에서 가장 높은 단계
    when: str
    items: tuple[RecentItem, ...]
    more_href: str  # 그 현장의 판정 내역


@dataclass(frozen=True, slots=True)
class HomeView:
    target_date: str
    sites: tuple[SiteSummary, ...]
    tiles: tuple[CountTile, ...]
    recent: tuple[RecentRun, ...]
    forecast_status: str
    forecast_issued: str | None
    rule_version: str | None
    rule_verified: bool
    message: str | None
    message_is_error: bool


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
    work: str
    verdict: str
    issued: str
    rule_version: str
    note: str | None


@dataclass(frozen=True, slots=True)
class FilterLink:
    label: str
    count: int
    href: str
    selected: bool


@dataclass(frozen=True, slots=True)
class HistoryView:
    rows: tuple[HistoryRow, ...]
    filters: tuple[FilterLink, ...]
    site_options: tuple[SiteOption, ...]
    selected_site_id: int | None
    selected_verdict: str
    page: int
    prev_href: str | None
    next_href: str | None
