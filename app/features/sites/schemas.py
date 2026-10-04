from dataclasses import dataclass
from datetime import time
from typing import Literal

# 기준표가 있으면 판정한다(원문 대조 전이면 그 표시를 함께). 없으면 판정하지 않는다(D-017).
BasisStatus = Literal["판정 · 원문 대조 필요", "판정 · 원문 확인됨", "기준 미확인"]


@dataclass(frozen=True, slots=True)
class SiteRecord:
    """다른 기능(판정)이 읽는 현장 정보."""

    site_id: int
    name: str
    address: str
    latitude_deg: float
    longitude_deg: float
    grid_nx: int
    grid_ny: int
    work_start_local: time  # KST
    work_end_local: time
    work_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SiteForm:
    """화면 입력값 그대로(검증 실패 시 다시 보여주기 위해 문자열로 둔다)."""

    name: str = ""
    address: str = ""
    latitude: str = ""
    longitude: str = ""
    work_start: str = "07:00"
    work_end: str = "17:00"
    work_types: tuple[str, ...] = ("철골 작업",)


@dataclass(frozen=True, slots=True)
class SiteInput:
    name: str
    address: str
    latitude_deg: float
    longitude_deg: float
    grid_nx: int
    grid_ny: int
    work_start_local: time
    work_end_local: time
    work_types: tuple[str, ...]


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
    site_id: int | None  # None이면 새 현장 등록
    form: SiteForm
    grid_text: str | None
    work_type_options: tuple[WorkTypeOption, ...]
    errors: tuple[str, ...]
    saved: bool
