from dataclasses import dataclass
from typing import Literal

Role = Literal["coordinator", "assignee", "viewer", "board"]
ParticipantKind = Literal["prime", "subcontractor"]
Category = Literal["subcontractor", "supplier", "equipment", "supervision"]

ROLE_LABELS: dict[Role, str] = {
    "coordinator": "조정자",
    "assignee": "담당자",
    "viewer": "열람자",
    "board": "게시(현장 TV)",
}
KIND_LABELS: dict[ParticipantKind, str] = {"prime": "원청", "subcontractor": "협력업체"}
# 참여 업체 구분(D-066). 원청이 아닌 업체의 구분이며 순서가 선택 목록 순서다.
CATEGORY_LABELS: dict[Category, str] = {
    "subcontractor": "협력업체",
    "supplier": "자재 공급",
    "equipment": "장비 임대",
    "supervision": "감리·CM",
}
# 직책 추천어(자유 입력 가능). 직책은 표시·연락용이고 권한과 무관하다(D-066).
JOB_TITLE_SUGGESTIONS = ("현장대리인", "반장", "공무", "안전관리자", "품질관리자", "기사", "감리원")
# 연락처(전화·메모)를 볼 수 있는 역할. 열람자(감리)에게는 이름·직책만 보인다(D-066).
CONTACT_DETAIL_ROLES: tuple[Role, ...] = ("coordinator", "assignee")
# 현장 수정·작업 일정·판정 실행·참여자 관리(D-057). 조치 처리 권한은 C06에서 따로 정한다.
MANAGE_ROLES: tuple[Role, ...] = ("coordinator",)
ALL_ROLES: tuple[Role, ...] = ("coordinator", "assignee", "viewer")
# 게시(D-067): 현장 공용 화면 계정. 게시 화면만 열고 다른 화면은 ALL_ROLES 범위라 열리지 않는다.
BOARD_ROLES: tuple[Role, ...] = ("board", *ALL_ROLES)
ASSIGNABLE_ROLES: tuple[Role, ...] = (*ALL_ROLES, "board")
# 변경 제안(초안·영향 검토로 보내기). 확정·철회(남의 제안)는 조정자만(D-057 A2, C05).
PROPOSE_ROLES: tuple[Role, ...] = ("coordinator", "assignee")
# 후속 조치 수행·검증을 맡을 수 있는 역할(C06). 열람자는 맡지 않는다.
ACTION_ROLES: tuple[Role, ...] = ("coordinator", "assignee")


@dataclass(frozen=True, slots=True)
class SiteMember:
    """현장의 활성 참여자 한 명. 조치 담당·검증자 고르기와 권한 확인에 쓴다."""

    site_id: int
    user_id: int
    display_name: str
    participant_id: int
    organization_name: str
    role: Role


@dataclass(frozen=True, slots=True)
class RosterPerson:
    """명부의 사람(삭제 안 됨). 조치 담당으로 고를 때 쓴다. user_id가 없으면 계정 미연결."""

    contact_id: int
    site_id: int
    participant_id: int
    name: str
    job_title: str
    user_id: int | None


@dataclass(frozen=True, slots=True)
class MemberView:
    membership_id: int
    display_name: str
    email: str | None  # 조정자에게만 보인다
    role_label: str
    granted_text: str  # KST
    is_me: bool


@dataclass(frozen=True, slots=True)
class ContactView:
    contact_id: int
    name: str
    job_title: str
    phone: str | None  # 열람자에게는 None(숨김)
    memo: str | None
    account_text: str | None  # 계정 연결 상태. None = 미연결


@dataclass(frozen=True, slots=True)
class ParticipantView:
    participant_id: int
    organization_name: str
    kind_label: str  # 원청 또는 구분 이름
    is_prime: bool
    category: str  # 수정 폼 기본값(원청은 빈 값)
    trade_note: str
    business_no: str | None  # 조정자에게만
    joined_on: str  # YYYY-MM-DD 또는 빈 값
    status_text: str  # "참여 중 · 10/01부터" / "참여 종료 · 10/16"
    is_ended: bool
    members: tuple[MemberView, ...]
    contacts: tuple[ContactView, ...]


@dataclass(frozen=True, slots=True)
class RoleOption:
    value: Role
    label: str
    selected: bool


@dataclass(frozen=True, slots=True)
class Option:
    value: str
    label: str
    selected: bool = False


@dataclass(frozen=True, slots=True)
class ParticipantOption:
    """작업 실행 업체·조치 담당으로 고를 수 있는 참여 중 업체."""

    participant_id: int
    name: str
    group_label: str  # 원청·협력업체·자재 공급·장비 임대·감리·CM


@dataclass(frozen=True, slots=True)
class ParticipantForm:
    organization_name: str = ""
    category: str = "subcontractor"
    trade_note: str = ""
    business_no: str = ""
    joined_on: str = ""
    confirm_same_name: bool = False  # 같은 이름 업체가 있어도 따로 등록


@dataclass(frozen=True, slots=True)
class ContactForm:
    name: str = ""
    job_title: str = ""
    phone: str = ""
    memo: str = ""


@dataclass(frozen=True, slots=True)
class MemberForm:
    email: str = ""
    role: str = "assignee"
    contact_id: str = ""  # 명부의 사람과 연결(선택)
    same_name: str = ""  # "" | "attach:<participant_id>" | "separate"


@dataclass(frozen=True, slots=True)
class MembersView:
    site_id: int
    site_name: str
    my_role_label: str
    can_manage: bool
    participants: tuple[ParticipantView, ...]
    role_options: tuple[RoleOption, ...]
    category_options: tuple[Option, ...] = ()
    contact_options: tuple[Option, ...] = ()  # 계정 미연결 명부(참여자 추가 시 연결)
    job_titles: tuple[str, ...] = JOB_TITLE_SUGGESTIONS
    member_form: MemberForm = MemberForm()
    participant_form: ParticipantForm = ParticipantForm()
    # 같은 이름 업체 경고: 업체 등록이면 확인 상자, 참여자 추가면 붙일 업체 선택지
    participant_same_name: tuple[str, ...] = ()
    member_same_name: tuple[Option, ...] = ()
    errors: tuple[str, ...] = ()
    message: str | None = None
