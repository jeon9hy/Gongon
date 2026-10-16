from dataclasses import dataclass
from datetime import date

# 현장 조회 범위. 로그인 사용자는 teams가 준 참여 현장 ID, None은 시스템 작업(매시 자동 판정)의
# 전체 현장이다. 기본값을 두지 않아 호출하는 쪽이 반드시 범위를 정하게 한다(D-057).
SiteScope = frozenset[int] | None


@dataclass(frozen=True, slots=True)
class SiteRecord:
    """다른 기능(판정)이 읽는 현장 정보."""

    site_id: int
    name: str
    address: str  # 대표 주소(도로명 우선, 없으면 지번)
    road_address: str  # 없으면 빈 문자열
    lot_address: str
    latitude_deg: float
    longitude_deg: float
    grid_nx: int
    grid_ny: int
    # 공종·작업 시간은 현장이 아니라 작업 일정마다 정한다(D-059).
    work_start_date: date | None  # 작업 기간(양 끝 포함). None이면 제한 없음
    work_end_date: date | None

    def works_on(self, day: date) -> bool:
        if self.work_start_date is not None and day < self.work_start_date:
            return False
        return self.work_end_date is None or day <= self.work_end_date

    def period_text(self) -> str | None:
        if self.work_start_date is None and self.work_end_date is None:
            return None
        start = "" if self.work_start_date is None else f"{self.work_start_date:%Y-%m-%d}"
        end = "" if self.work_end_date is None else f"{self.work_end_date:%Y-%m-%d}"
        return f"{start}~{end}"


@dataclass(frozen=True, slots=True)
class SiteForm:
    """화면 입력값 그대로(검증 실패 시 다시 보여주기 위해 문자열로 둔다)."""

    name: str = ""
    road_address: str = ""
    lot_address: str = ""
    latitude: str = ""
    longitude: str = ""
    work_start_date: str = ""
    work_end_date: str = ""


@dataclass(frozen=True, slots=True)
class SiteInput:
    name: str
    address: str  # 대표 주소(도로명 우선)
    road_address: str
    lot_address: str
    latitude_deg: float
    longitude_deg: float
    grid_nx: int
    grid_ny: int
    work_start_date: date
    work_end_date: date


@dataclass(frozen=True, slots=True)
class SiteListItem:
    href: str
    name: str
    address: str
    period: str | None  # 짧은 작업 기간(예: 26.10.04 ~ 11.03 형식). 기간이 없으면 None
    selected: bool


@dataclass(frozen=True, slots=True)
class SitesView:
    items: tuple[SiteListItem, ...]
    site_id: int | None  # None이면 새 현장 등록
    form: SiteForm
    grid_text: str | None
    errors: tuple[str, ...]
    saved: bool
    deleted: bool = False  # 방금 현장을 삭제하고 돌아왔는가
    can_edit: bool = True  # 새 현장 등록이거나 이 현장의 조정자
