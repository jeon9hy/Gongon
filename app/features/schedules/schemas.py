from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True, slots=True)
class WorkItemRecord:
    """다른 기능(판정)이 읽는 작업 한 건."""

    item_id: int
    site_id: int
    work_type: str
    work_date: date
    start_local: time
    end_local: time
    location: str
    memo: str

    @property
    def label(self) -> str:
        return f"{self.work_type} · {self.location}" if self.location else self.work_type


@dataclass(frozen=True, slots=True)
class WorkItemForm:
    """화면 입력값 그대로(검증 실패 시 다시 보여주기 위해 문자열로 둔다)."""

    work_type: str = ""
    work_date: str = ""
    start: str = ""
    end: str = ""
    location: str = ""
    memo: str = ""


@dataclass(frozen=True, slots=True)
class SiteChoice:
    site_id: int
    name: str
    selected: bool


@dataclass(frozen=True, slots=True)
class CalendarDay:
    """달력 한 칸."""

    day: date
    href: str  # 누르면 이 날짜를 고른 화면
    in_month: bool  # 보고 있는 달의 날짜인가(앞뒤 달 칸은 흐리게)
    is_today: bool
    is_target: bool  # 내일(판정 대상 날짜)
    in_period: bool  # 현장 작업 기간 안
    selected: bool
    items: tuple[WorkItemRecord, ...]  # 칸에 보이는 작업(최대 CELL_ITEMS개)
    more: int  # 칸에 다 못 보인 작업 수


@dataclass(frozen=True, slots=True)
class DayDetail:
    """고른 날짜의 상세(오른쪽 패널)."""

    day: date
    day_text: str  # "10월 9일(금)"
    is_target: bool
    can_add: bool  # 내일 이후·작업 기간 안이면 작업을 추가할 수 있다
    note: str | None  # 추가할 수 없는 이유 등
    items: tuple[WorkItemRecord, ...]


@dataclass(frozen=True, slots=True)
class ScheduleView:
    sites: tuple[SiteChoice, ...]
    site_id: int | None
    site_name: str
    period_text: str | None
    month_title: str  # "2026년 10월"
    prev_href: str
    next_href: str
    this_month_href: str
    weeks: tuple[tuple[CalendarDay, ...], ...]  # 월요일 시작 7칸씩
    detail: DayDetail | None
    work_types: tuple[str, ...]  # 고를 수 있는 공종(현장에 등록한 공종)
    form: WorkItemForm
    errors: tuple[str, ...]
    message: str | None
