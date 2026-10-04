from dataclasses import dataclass
from typing import Literal

# 총정리 §1 표에 값이 있는 기준은 "원문 대조 필요", §3 4단계처럼 값이 없는 기준은 "기준 미확인"
BasisStatus = Literal["원문 대조 필요", "기준 미확인"]


@dataclass(frozen=True, slots=True)
class WorkType:
    label: str
    basis: BasisStatus


@dataclass(frozen=True, slots=True)
class SiteSetting:
    site_id: int
    name: str
    address: str
    latitude_deg: float
    longitude_deg: float
    work_types: tuple[str, ...]  # WorkType.label
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
class WorkTypeOption:
    label: str
    basis: BasisStatus
    checked: bool


@dataclass(frozen=True, slots=True)
class SitesView:
    items: tuple[SiteListItem, ...]
    site: SiteSetting
    grid_text: str
    work_type_options: tuple[WorkTypeOption, ...]
    unconfirmed_labels: tuple[str, ...]
