from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SiteSetting:
    site_id: int
    name: str
    address: str
    latitude_deg: float
    longitude_deg: float
    steel_enabled: bool
    work_start: str  # 현장 현지 시각(KST) "HH:MM"
    work_end: str
    notify_enabled: bool
    phone: str


@dataclass(frozen=True, slots=True)
class SiteListItem:
    href: str
    name: str
    summary: str
    selected: bool


@dataclass(frozen=True, slots=True)
class SitesView:
    items: tuple[SiteListItem, ...]
    site: SiteSetting
    grid_text: str
