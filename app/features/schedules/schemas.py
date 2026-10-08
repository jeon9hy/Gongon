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
class DayGroup:
    day_text: str  # "10월 9일(금)"
    is_target: bool  # 내일(판정 대상 날짜)
    items: tuple[WorkItemRecord, ...]


@dataclass(frozen=True, slots=True)
class ScheduleView:
    sites: tuple[SiteChoice, ...]
    site_id: int | None
    site_name: str
    period_text: str | None
    days: tuple[DayGroup, ...]
    work_types: tuple[str, ...]  # 고를 수 있는 공종(현장에 등록한 공종)
    form: WorkItemForm
    errors: tuple[str, ...]
    message: str | None
