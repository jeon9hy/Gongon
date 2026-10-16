from dataclasses import dataclass
from typing import Literal

Role = Literal["coordinator", "assignee", "viewer"]
ParticipantKind = Literal["prime", "subcontractor"]

ROLE_LABELS: dict[Role, str] = {"coordinator": "조정자", "assignee": "담당자", "viewer": "열람자"}
KIND_LABELS: dict[ParticipantKind, str] = {"prime": "원청", "subcontractor": "협력업체"}
# 현장 수정·작업 일정·판정 실행·참여자 관리(D-057). 조치 처리 권한은 C06에서 따로 정한다.
MANAGE_ROLES: tuple[Role, ...] = ("coordinator",)
ALL_ROLES: tuple[Role, ...] = ("coordinator", "assignee", "viewer")
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
class MemberView:
    membership_id: int
    display_name: str
    email: str | None  # 조정자에게만 보인다
    role_label: str
    granted_text: str  # KST
    is_me: bool


@dataclass(frozen=True, slots=True)
class ParticipantView:
    organization_name: str
    kind_label: str
    members: tuple[MemberView, ...]


@dataclass(frozen=True, slots=True)
class RoleOption:
    value: Role
    label: str
    selected: bool


@dataclass(frozen=True, slots=True)
class MembersView:
    site_id: int
    site_name: str
    my_role_label: str
    can_manage: bool
    participants: tuple[ParticipantView, ...]
    role_options: tuple[RoleOption, ...]
    email: str = ""
    errors: tuple[str, ...] = ()
    message: str | None = None
