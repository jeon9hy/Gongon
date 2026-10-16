from dataclasses import dataclass
from typing import Literal

# 변경 원인(product.md §1). 여러 원인이면 복수로 고른다. 기상은 그중 하나다.
REASON_LABELS: dict[str, str] = {
    "schedule": "공정·선행 작업",
    "labor": "인력",
    "equipment": "장비",
    "material": "자재",
    "design": "도면·설계",
    "quality": "품질·검측",
    "safety": "안전·작업 허가",
    "area": "구역·동선",
    "cost": "비용·계약",
    "external": "외부 조건",
    "weather": "기상",
}

RevisionStatus = Literal["draft", "review", "confirmed", "superseded", "withdrawn"]
STATUS_LABELS: dict[str, str] = {
    "draft": "초안",
    "review": "영향 검토",
    "confirmed": "확정",
    "superseded": "대체됨",
    "withdrawn": "철회",
}
OPEN_STATUSES: tuple[str, ...] = ("draft", "review")


@dataclass(frozen=True, slots=True)
class ChangeForm:
    """변경 제안 입력(문자열 그대로). plan_version은 제안 화면을 연 때의 작업 계획 버전."""

    work_item_id: str = ""
    case_id: str = ""  # 비어 있으면 새 변경 건, 있으면 그 건의 재변경
    title: str = ""
    after_work_date: str = ""
    after_start: str = ""
    after_end: str = ""
    after_location: str = ""
    reasons: tuple[str, ...] = ()
    basis_note: str = ""
    plan_version: str = ""
    submit: str = "draft"  # draft: 초안 저장, review: 영향 검토로 보냄


@dataclass(frozen=True, slots=True)
class ReasonOption:
    code: str
    label: str
    checked: bool


@dataclass(frozen=True, slots=True)
class ChangeFormView:
    site_id: int
    site_name: str
    work_item_id: int
    work_label: str
    current_text: str  # 지금 계획 "10/05(월) 09:00-12:00 · A구역"
    current_date: str
    current_start: str
    plan_version: int
    case_id: int | None
    form: ChangeForm
    reasons: tuple[ReasonOption, ...]
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChangeListItem:
    href: str
    title: str
    work_label: str
    status: str
    status_label: str
    version_text: str  # "v2"
    after_text: str
    reasons_text: str
    updated_text: str


@dataclass(frozen=True, slots=True)
class SiteFilter:
    site_id: int
    name: str
    selected: bool


@dataclass(frozen=True, slots=True)
class ChangesView:
    sites: tuple[SiteFilter, ...]
    site_id: int | None
    show: Literal["open", "all"]
    items: tuple[ChangeListItem, ...]
    open_href: str
    all_href: str


@dataclass(frozen=True, slots=True)
class RevisionView:
    revision_id: int
    number: int
    status: str
    status_label: str
    before_text: str
    after_text: str
    reasons_text: str
    basis_note: str
    history: tuple[str, ...]  # "10/04 15:00 제안 · 테스트 조정자" 등 시간순
    withdraw_reason: str | None
    can_submit: bool
    can_confirm: bool
    can_withdraw: bool


@dataclass(frozen=True, slots=True)
class ChangeDetailView:
    case_id: int
    site_id: int
    site_name: str
    title: str
    work_label: str
    current_plan_text: str
    current_version_text: str | None  # 현재 확정 버전 "v2", 없으면 None
    revisions: tuple[RevisionView, ...]  # 최신 버전 먼저
    rechange_href: str | None  # 진행 중 버전이 없고 제안 권한이 있으면
    confirm_key: str  # 확정 버튼의 재전송 식별값(화면을 열 때 새로 만든다)
    errors: tuple[str, ...] = ()
    message: str | None = None
