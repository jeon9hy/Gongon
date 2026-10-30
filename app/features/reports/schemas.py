from dataclasses import dataclass


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
