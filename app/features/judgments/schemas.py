"""판정 화면이 쓰는 표시용 모델. 판정 계산은 engine/judgment가 하고, 여기서는 보여줄 값만 담는다."""

from dataclasses import dataclass, field
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
    checked_short: str | None = None  # 홈과 같은 짧은 점검 시각
    work_options: "tuple[WorkOption, ...]" = ()  # 상세 카드에서 고를 수 있는 작업(2개 이상일 때)
    detail_open: bool = False  # 작업·요소·시각을 골라 들어왔으면 시간대별 예보 모달을 바로 연다
    can_run: bool = True  # 7일 중 작업일이 있어 판정할 수 있는가
    # 7일 표 묶음(C04-31): 업체별(기본)·위치별. 묶음 줄을 누르면 작업 종류별 줄이 펼쳐진다.
    week_groups: "tuple[WeekGroupRow, ...]" = ()
    week_place_groups: "tuple[WeekGroupRow, ...]" = ()


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
class BoardGroup:
    """홈 오늘 보드의 묶음 카드(C04-31): 업체별 또는 위치별. 끝나지 않은 작업만 담는다."""

    label: str  # 업체 이름 · 동·층
    sub: str  # 업체별: 업종 메모, 위치별: "대성골조 외 1"
    time_text: str  # 묶음의 가장 이른 시작~가장 늦은 끝
    items: tuple[BoardItem, ...]  # 시작 시각 순
    issues: tuple[str, ...]  # 하위 작업에서 걸린 점검 항목(중복 없이)
    phase: Literal["before", "now"]  # 하나라도 진행 중이면 now
    unassigned: bool = False  # 업체 미정 묶음(점검 문제)


@dataclass(frozen=True, slots=True)
class DayBoard:
    key: Literal["today", "tomorrow"]
    title: str  # "오늘"·"내일"
    date_text: str
    items: tuple[BoardItem, ...]
    criteria: tuple[tuple[str, int], ...]  # (점검 항목 이름, 걸린 작업 수), 걸린 것만
    add_href: str = ""  # 같은 현장·날짜의 작업 추가 모달
    groups: tuple[BoardGroup, ...] = ()  # 오늘만: 업체별
    place_groups: tuple[BoardGroup, ...] = ()  # 오늘만: 위치별(동·층)

    @property
    def ready(self) -> int:
        return sum(1 for i in self.items if not i.issues)


@dataclass(frozen=True, slots=True)
class HomeIndexDay:
    """홈의 이번 주 공온지수 한 칸. 현장이 여럿이면 점수가 있는 현장의 평균(D-078)."""

    label: str  # "10/17(토)"
    short: str  # "토 17" (좁은 화면)
    is_tomorrow: bool
    score: int | None  # None: 점수 없음(판정 전·예보 전·작업 없음)
    sub: str  # 점수가 없을 때 이유, 현장이 여럿이면 '현장 n곳'
    href: str
    reference: bool = False  # 먼 날 예보(중기)로 계산한 참고 점수: 글 대신 점선 원으로 구분


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
class DayTypeItem:
    """날 패널 묶음을 펼쳤을 때의 작업 한 건."""

    item_id: int
    work_type: str
    where: str  # 업체별 묶음이면 위치, 위치별 묶음이면 업체
    time_text: str
    verdict: str | None
    href: str


@dataclass(frozen=True, slots=True)
class DayGroupRow:
    """7일 공온지수 날 패널의 묶음 한 줄(D-085): 업체별(현장 공종 단위) 또는 위치별(동·층).

    2건 이상이면 눌러서 하위 작업(items)을 펼친다. 중지 검토가 있으면 처음부터 펼친다.
    """

    label: str  # 업체 이름 · 동·층
    sub: str  # 업체별: 업종 메모, 위치별: "대성골조 외 1"
    time_text: str  # 묶음의 가장 이른 시작~가장 늦은 끝
    count: int
    verdict: str | None  # 하위 작업 중 가장 높은 단계. None은 판정 전
    href: str  # 그 작업의 판정 상세. 판정이 없으면 작업 일정 그날
    items: tuple[DayTypeItem, ...]  # 시작 시각 순
    unassigned: bool = False  # 업체 미정 묶음(점검 문제)


@dataclass(frozen=True, slots=True)
class DayPanel:
    """홈 7일 공온지수의 하루(개발자 요청 2026-10-17): 원을 누르면 그날 판정 요약이 슬라이드처럼."""

    label: str  # "내일" · "10/19(월)"
    total: int
    go: int
    check: int
    stop: int
    rows: tuple[DayGroupRow, ...]  # 업체별
    href: str  # 공온 판정(대시보드)
    add_href: str = ""  # 같은 현장·날짜의 작업 추가 모달
    place_rows: tuple[DayGroupRow, ...] = ()  # 위치별(동·층)


@dataclass(frozen=True, slots=True)
class InboxItem:
    """홈 내 차례 한 줄(C04-44): 무엇을, 왜, 어디서, 바로 할 일 하나.

    같은 일(같은 꼬리표·공정 또는 위치)은 한 줄로 합치고 건수·현장 수를 보인다(C04-51)."""

    tag: str  # "업체 미지정" · "검증" · "막힘" · "응답" · "변경 검토" · "내일 확인 필요"
    tone: Literal["stop", "warn", "blue", "plain"]
    title: str
    meta: str
    href: str
    action: str  # 버튼 글자
    late: str = ""  # 늦음 표시(빨간 글자)
    detail: str = ""  # 마우스를 올리면 보이는 자세한 이유(예: 같은 곳·같은 시간 상대 작업)
    work: str = ""  # 공정(작업 이름·조치 이름) — 공정별 묶기 열쇠
    place: str = ""  # 위치(작업 위치, 없으면 현장) — 위치별 묶기 열쇠
    site: str = ""
    count: int = 1  # 합친 건수
    where: str = ""  # 위치 · 현장(합치면 '101동 3층 슬래브 · 현장 6곳')


@dataclass(frozen=True, slots=True)
class InboxGroup:
    key: str
    title: str
    hint: str
    by_work: tuple[InboxItem, ...]  # 공정별로 합친 줄
    by_place: tuple[InboxItem, ...]  # 위치별로 합친 줄
    total: int  # 합치기 전 건수
    more_href: str  # 전체 목록 화면


@dataclass(frozen=True, slots=True)
class HomeInbox:
    """홈 첫 화면의 챙길 일(C04-44·C04-51, D-099).

    오늘 작업의 점검 문제는 왼쪽 오늘 일정에 보이고 맨 위 '먼저 할 일'을 고르는 데만 쓴다.
    오른쪽 카드는 넘겨 보는 소탭: (할 일) · 확인 대기 · 보류 · 결정 대기."""

    groups: tuple[InboxGroup, ...]  # 소탭 순서. 할 일은 있을 때만
    today: tuple[InboxItem, ...]  # 오늘 작업 점검 문제(공정별로 합친 줄)
    today_total: int = 0

    @property
    def total(self) -> int:
        return self.today_total + sum(g.total for g in self.groups)

    @property
    def first(self) -> InboxItem | None:
        if self.today:
            return self.today[0]
        return next((g.by_work[0] for g in self.groups if g.by_work), None)


@dataclass(frozen=True, slots=True)
class HomeWeather:
    """홈 날씨 카드. 관측이 아니라 예보이며 없는 값은 대시로 보인다(채우지 않는다)."""

    site_name: str
    more_sites: int  # 다른 현장 수(현장 전체로 볼 때)
    hour_text: str  # '14시 예보'
    issued_text: str  # '11:00 발표'
    sky: str | None
    temperature: str  # '14°'
    wind: str  # '3.2 m/s'
    humidity: str  # '60%'
    rain_probability: str  # '20%'
    precipitation: str  # 기상청 원문


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
    day_panels: tuple[DayPanel, ...] = ()  # index_days와 같은 7일, 같은 순서
    selected_site_id: int | None = None  # 고른 현장(전체면 None). 메뉴 링크가 이어받는다
    weather_now: HomeWeather | None = None  # 맨 위 날씨 카드(지금과 가장 가까운 예보 시각)
    single_site: bool = False  # 현장 하나만 보는 중(날씨 카드는 이때만)


@dataclass(frozen=True, slots=True)
class CriterionCard:
    label: str
    icon: str
    verdict: str
    peak_value: str
    unit: str
    peak_time: str | None
    peak_label: str
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
    chips: tuple[tuple[str, str], ...]  # (이름, 값) 판정 근거 정보
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
class WeekGroupRow:
    """7일 표의 묶음 한 줄(C04-31). 칸은 그날 묶음 안 작업 중 가장 높은 단계."""

    label: str  # 업체 이름 · 동·층
    sub: str  # 업체별: 업종 메모, 위치별: 업체 이름들
    count: int  # 7일 동안 묶음 안 작업 건수
    cells: tuple[WeekCell, ...]
    types: tuple[WeekRow, ...]  # 펼치면 보이는 작업 종류별 줄
    unassigned: bool = False


@dataclass(frozen=True, slots=True)
class WeekView:
    days: tuple[WeekDay, ...]
    rows: tuple[WeekRow, ...]
    # (날짜, 작업 id) → 그 작업의 칸. 홈 날 패널에서 묶음을 펼친 하위 작업 줄에 쓴다(D-085).
    items: dict[tuple[date, int], WeekCell] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkOption:
    label: str
    verdict: str
    href: str
    selected: bool
