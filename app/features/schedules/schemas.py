from dataclasses import dataclass, field
from datetime import date, time
from typing import Literal

from app.core.rules import BasisStatus


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
    performing_participant_id: int | None = None  # 실행 업체. None은 미지정
    plan_version: int = 1

    @property
    def label(self) -> str:
        return f"{self.work_type} · {self.location}" if self.location else self.work_type


@dataclass(frozen=True, slots=True)
class WorkItemForm:
    """화면 입력값 그대로(검증 실패 시 다시 보여주기 위해 문자열로 둔다)."""

    work_types: tuple[str, ...] = ()  # 고른 공종들. 공종마다 작업을 따로 만든다(D-059)
    work_date: str = ""  # 스크립트 없는 화면의 날짜 하나
    start: str = ""
    end: str = ""
    location: str = ""
    memo: str = ""
    work_dates: tuple[str, ...] = ()  # 달력에서 고른 날짜들. 날마다 같은 시간으로 작업을 만든다
    performing_participant_id: str = ""  # 빈 값은 실행 업체 미지정
    date_mode: str = "pick"  # pick: 날짜를 하나씩 고름, range: 기간 + 요일
    range_start: str = ""
    range_end: str = ""
    weekdays: tuple[str, ...] = ("0", "1", "2", "3", "4")  # 월=0. 기간 고르기의 기본은 평일


@dataclass(frozen=True, slots=True)
class WorkItemEditForm:
    """작업 계획 수정. 공종은 바꾸지 않는다(판정 묶음 기준). plan_version은 화면을 연 때의 버전."""

    work_date: str = ""
    start: str = ""
    end: str = ""
    location: str = ""
    memo: str = ""
    performing_participant_id: str = ""
    plan_version: str = ""


@dataclass(frozen=True, slots=True)
class PlanValues:
    """계획 한 벌(작업 일정 수정과 C05 변경 확정이 같은 저장 함수를 쓴다)."""

    work_date: date
    start_local: time
    end_local: time
    location: str
    memo: str
    performing_participant_id: int | None


PlanChangeResult = Literal["saved", "unchanged", "conflict", "missing"]


@dataclass(frozen=True, slots=True)
class ParticipantChoice:
    participant_id: int
    name: str  # 회사 이름
    selected: bool = False
    group_label: str = ""  # 원청·협력업체·자재 공급·장비 임대·감리·CM(선택 목록 묶음)


@dataclass(frozen=True, slots=True)
class WorkTypeChoice:
    label: str
    basis: BasisStatus
    selected: bool
    used: int  # 이 현장에 등록한 작업 수(많이 쓴 공종을 앞에 둔다)


@dataclass(frozen=True, slots=True)
class RevisionView:
    """작업 카드의 변경 이력 한 줄(바뀌기 전 값)."""

    plan_version: int
    summary: str  # 예: 10/06 08:00-12:00 · A구역 · 가상골조
    changed_text: str  # "10/04 15:00 테스트 조정자"


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
    addable: bool  # 작업을 추가할 수 있는 날(오늘 이후·작업 기간 안)
    items: tuple[WorkItemRecord, ...]  # 칸에 보이는 작업(최대 CELL_ITEMS개)
    more: int  # 칸에 다 못 보인 작업 수


@dataclass(frozen=True, slots=True)
class DayDetail:
    """고른 날짜의 상세(오른쪽 패널)."""

    day: date
    day_text: str  # "10월 9일(금)"
    is_target: bool
    can_add: bool  # 오늘 이후·작업 기간 안이면 작업을 추가할 수 있다
    note: str | None  # 추가할 수 없는 이유 등
    items: tuple[WorkItemRecord, ...]


@dataclass(frozen=True, slots=True)
class MonthChoice:
    """달 고르기 목록의 한 칸."""

    label: str  # "10월"
    href: str
    selected: bool  # 지금 보고 있는 달
    in_period: bool  # 현장 작업 기간과 겹치는 달
    is_target: bool  # 내일(판정 대상)이 든 달


@dataclass(frozen=True, slots=True)
class ScheduleView:
    sites: tuple[SiteChoice, ...]
    site_id: int | None
    site_name: str
    period_text: str | None
    month_title: str  # "2026년 10월"
    prev_href: str | None  # 작업 기간 밖이면 None
    next_href: str | None
    this_month_href: str
    month_groups: tuple[tuple[int, tuple[MonthChoice, ...]], ...]  # (연도, 그 해의 달들)
    weeks: tuple[tuple[CalendarDay, ...], ...]  # 월요일 시작 7칸씩
    detail: DayDetail | None
    work_types: tuple[WorkTypeChoice, ...]  # 고를 수 있는 공종(자주 쓴 순)
    form: WorkItemForm
    errors: tuple[str, ...]
    message: str | None
    participants: tuple[ParticipantChoice, ...] = ()  # 실행 업체로 고를 수 있는 참여 업체
    has_partners: bool = False  # 원청 말고 참여 중인 업체가 있나(없으면 작업 추가를 막는다)
    today_iso: str = ""  # 작업 추가 달력의 첫 날(지난 날은 고를 수 없다)
    now_hm: str = ""  # 오늘 작업은 이 시각 뒤에 시작해야 한다(D-064)
    period_start_iso: str = ""  # 현장 작업 기간(빈 값은 제한 없음)
    period_end_iso: str = ""
    participant_names: dict[int, str] = field(default_factory=dict)
    revisions: dict[int, tuple[RevisionView, ...]] = field(default_factory=dict)  # 고른 날 작업
    edit_item_id: int | None = None  # 수정에 실패한 작업(그 카드의 수정 칸을 연다)
    edit_errors: tuple[str, ...] = ()
