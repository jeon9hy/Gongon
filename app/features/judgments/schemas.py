"""판정 화면이 쓰는 표시용 모델. 판정 계산은 하지 않고 정해진 결과를 담는다(판정은 S03 엔진)."""

from dataclasses import dataclass
from typing import Literal

Element = Literal["rain", "wind", "snow"]
VerdictFilter = Literal["전체", "진행", "확인 필요", "중지 검토", "판정 불가"]


@dataclass(frozen=True, slots=True)
class ElementSeries:
    key: Element
    label: str
    unit: str
    threshold: float
    axis_max: float
    hourly_values: tuple[float, ...]  # HOURS 순서
    over_hours: frozenset[int]  # 기준 이상인 시각(정시, 0~23)


@dataclass(frozen=True, slots=True)
class WorkWindow:
    time_range: str
    verdict: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class WorkVerdict:
    """공종 하나의 내일 판정 요약. 기준이 없는 공종은 '확인 필요'까지만 낸다."""

    work_type: str
    time_range: str
    verdict: str
    reason: str
    detail_href: str | None


@dataclass(frozen=True, slots=True)
class NoticeItem:
    work: str
    verdict: str
    reason: str


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
class DashboardView:
    site_name: str
    target_date: str
    work_hours: str
    forecast_issued: str
    rule_version: str
    work_verdicts: tuple[WorkVerdict, ...]
    windows: tuple[WorkWindow, ...]
    tiles: tuple[Tile, ...]
    tabs: tuple[Tab, ...]
    bars: tuple[Bar, ...]
    selected_value: str
    selected_caption: str
    threshold_bottom_px: int
    threshold_text: str
    collection_status: str
    judged_at: str
    grid: str
    notice_title: str
    notice_items: tuple[NoticeItem, ...]
    notice_disclaimer: str


@dataclass(frozen=True, slots=True)
class Criterion:
    label: str
    code: str
    icon: str
    verdict: str
    peak_value: str
    unit: str
    peak_time: str | None
    rule_text: str
    source: str


@dataclass(frozen=True, slots=True)
class HourRow:
    time: str
    rain: str
    wind: str
    snow: str
    rain_over: bool
    verdict: str
    calculation: str
    peak: bool


@dataclass(frozen=True, slots=True)
class DetailView:
    site_name: str
    target_date: str
    work_range: str
    verdict: str
    chips: tuple[str, ...]
    criteria: tuple[Criterion, ...]
    rows: tuple[HourRow, ...]


@dataclass(frozen=True, slots=True)
class HistoryRow:
    judgment_id: int | None  # 상세 화면이 있는 판정만 값이 있다
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
    site_options: tuple[str, ...]
    selected_site: str
    selected_verdict: str
