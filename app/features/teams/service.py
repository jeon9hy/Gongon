"""현장 참여 업체·멤버십·역할(C03-2, D-057). 현장 접근 범위와 역할 확인은 모두 여기를 거친다.

- 비참여 현장은 404(존재를 드러내지 않음), 역할 부족은 403.
- 같은 회사여도 멤버십이 없으면 볼 수 없다. 회사 공통 관리자는 없다.
- 조정자는 원청 소속만 될 수 있다. 마지막 조정자는 회수할 수 없다.
"""

from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser, UserInfo
from app.features.teams import repository
from app.features.teams.models import ProjectMembership, ProjectParticipant
from app.features.teams.schemas import (
    ALL_ROLES,
    KIND_LABELS,
    MANAGE_ROLES,
    PROPOSE_ROLES,
    ROLE_LABELS,
    MembersView,
    MemberView,
    ParticipantKind,
    ParticipantView,
    Role,
    RoleOption,
)
from engine.kst import KST

NOT_FOUND = "현장을 찾을 수 없습니다"
FORBIDDEN = "이 현장에서 이 작업을 할 권한이 없습니다"


def site_ids_for(session: Session, user_id: int) -> frozenset[int]:
    """활성 멤버십이 있는 현장. 다른 기능은 이 범위로 목록·조회를 제한한다."""
    return repository.active_site_ids(session, user_id, ALL_ROLES)


def managed_site_ids(session: Session, user_id: int) -> frozenset[int]:
    return repository.active_site_ids(session, user_id, MANAGE_ROLES)


def role_on(session: Session, user_id: int, site_id: int) -> Role | None:
    membership = repository.active_membership(session, user_id, site_id)
    return None if membership is None else cast(Role, membership.role)


def require_role(
    session: Session, user: CurrentUser, site_id: int, allowed: tuple[Role, ...]
) -> Role:
    role = role_on(session, user.user_id, site_id)
    if role is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if role not in allowed:
        raise HTTPException(status_code=403, detail=FORBIDDEN)
    return role


def accessible_site_ids(
    user: auth_service.CurrentUserDep, session: Annotated[Session, Depends(get_session)]
) -> frozenset[int]:
    """라우터 의존성: 로그인 사용자가 볼 수 있는 현장 ID."""
    return site_ids_for(session, user.user_id)


AccessibleSitesDep = Annotated[frozenset[int], Depends(accessible_site_ids)]


def manageable_site_ids(
    user: auth_service.CurrentUserDep, session: Annotated[Session, Depends(get_session)]
) -> frozenset[int]:
    """라우터 의존성: 내가 조정자인 현장. 화면에서 실행·추가·삭제 버튼을 보일지 정한다.

    버튼을 숨기는 것은 안내일 뿐이며 권한은 각 서비스의 require_role이 확인한다.
    """
    return managed_site_ids(session, user.user_id)


ManagedSitesDep = Annotated[frozenset[int], Depends(manageable_site_ids)]


def proposable_site_ids(
    user: auth_service.CurrentUserDep, session: Annotated[Session, Depends(get_session)]
) -> frozenset[int]:
    """라우터 의존성: 변경을 제안할 수 있는 현장(조정자·담당자). 버튼 표시용이다."""
    return repository.active_site_ids(session, user.user_id, PROPOSE_ROLES)


ProposableSitesDep = Annotated[frozenset[int], Depends(proposable_site_ids)]


def participant_labels(session: Session, site_id: int) -> dict[int, str]:
    """현장 참여 업체 ID → "회사 이름 · 원청/협력업체"(원청 먼저). 실행 업체 고르기·표시에 쓴다."""
    participants = repository.participants(session, site_id)
    names = auth_service.organization_names(session, (p.organization_id for p in participants))
    return {
        p.id: f"{names.get(p.organization_id, '이름 없음')} · "
        f"{KIND_LABELS[cast(ParticipantKind, p.kind)]}"
        for p in participants
    }


def add_founder(session: Session, site_id: int, user: CurrentUser, now: datetime) -> None:
    """현장을 만든 사람의 회사를 원청, 본인을 조정자로 둔다. 커밋은 호출한 현장 서비스가 한다."""
    participant = ProjectParticipant(
        site_id=site_id, organization_id=user.organization_id, kind="prime"
    )
    session.add(participant)
    session.flush()
    session.add(_membership(participant, user.user_id, "coordinator", user.user_id, now))


def add_member(
    session: Session, site_id: int, actor: CurrentUser, email: str, role_raw: str, now: datetime
) -> tuple[str, ...]:
    """가입한 사용자를 참여자로 추가한다. 그 회사가 처음이면 협력업체로 참여시킨다."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    if role_raw not in ALL_ROLES:
        return ("역할을 고르세요.",)
    role: Role = role_raw
    target = auth_service.find_user_by_email(session, email)
    if target is None or not target.is_active:
        return ("가입한 사용자의 이메일을 입력하세요. 초대 메일은 아직 보내지 않습니다.",)
    if repository.active_membership(session, target.user_id, site_id) is not None:
        return ("이미 이 현장에 참여 중입니다. 역할을 바꾸려면 회수한 뒤 다시 추가하세요.",)
    participant = repository.participant_of(session, site_id, target.organization_id)
    if role == "coordinator" and (participant is None or participant.kind != "prime"):
        return ("조정자는 원청 소속 사용자만 될 수 있습니다.",)
    if participant is None:
        participant = ProjectParticipant(
            site_id=site_id, organization_id=target.organization_id, kind="subcontractor"
        )
        session.add(participant)
        session.flush()
    session.add(_membership(participant, target.user_id, role, actor.user_id, now))
    try:
        session.commit()
    except IntegrityError:
        # 같은 사용자를 동시에 두 번 추가한 경우(활성 멤버십 고유 인덱스)
        session.rollback()
        return ("이미 이 현장에 참여 중입니다.",)
    return ()


def revoke_member(
    session: Session, site_id: int, actor: CurrentUser, membership_id: int, now: datetime
) -> tuple[str, ...]:
    require_role(session, actor, site_id, MANAGE_ROLES)
    coordinators = repository.lock_active_coordinators(session, site_id)
    membership = session.get(ProjectMembership, membership_id)
    if membership is None or membership.site_id != site_id or membership.revoked_at is not None:
        session.rollback()
        raise HTTPException(status_code=404, detail="참여자를 찾을 수 없습니다")
    if membership.role == "coordinator" and len(coordinators) <= 1:
        session.rollback()
        return ("마지막 조정자는 회수할 수 없습니다. 다른 조정자를 먼저 추가하세요.",)
    membership.revoked_at = now
    membership.revoked_by_user_id = actor.user_id
    session.commit()
    return ()


def grant_existing_site(session: Session, site_id: int, email: str, now: datetime) -> str:
    """참여 업체가 없는 기존 현장(0010 이전)에 개발자가 명시한 사용자를 원청 조정자로 둔다.

    소유자를 추정하지 않는다. 이미 원청이 있으면 그 회사 사용자만 조정자로 추가한다.
    """
    user = auth_service.find_user_by_email(session, email)
    if user is None or not user.is_active:
        raise ValueError(f"가입한 활성 사용자가 아님: {email}")
    if repository.active_membership(session, user.user_id, site_id) is not None:
        raise ValueError("이미 이 현장에 참여 중")
    participants = repository.participants(session, site_id)
    prime = next((p for p in participants if p.kind == "prime"), None)
    if prime is not None and prime.organization_id != user.organization_id:
        raise ValueError("이 현장의 원청 회사 소속이 아님")
    try:
        if prime is None:
            prime = ProjectParticipant(
                site_id=site_id, organization_id=user.organization_id, kind="prime"
            )
            session.add(prime)
            session.flush()
        session.add(_membership(prime, user.user_id, "coordinator", None, now))
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ValueError(f"없는 현장이거나 동시에 지정됨: {site_id}") from error
    return f"현장 {site_id}: {user.display_name}({user.organization_name})을 조정자로 지정"


def build_members_view(
    session: Session,
    site_id: int,
    site_name: str,
    viewer: CurrentUser,
    email: str = "",
    role: str = "assignee",
    errors: tuple[str, ...] = (),
    message: str | None = None,
) -> MembersView:
    my_role = require_role(session, viewer, site_id, ALL_ROLES)
    can_manage = my_role in MANAGE_ROLES
    memberships = repository.active_memberships(session, site_id)
    users = auth_service.describe_users(session, (m.user_id for m in memberships))
    by_participant: dict[int, list[ProjectMembership]] = {}
    for m in memberships:
        by_participant.setdefault(m.participant_id, []).append(m)
    organization_names = {u.organization_id: u.organization_name for u in users.values()}
    participants = tuple(
        ParticipantView(
            organization_name=organization_names.get(p.organization_id, "참여자 없음"),
            kind_label=KIND_LABELS[cast(ParticipantKind, p.kind)],
            members=tuple(
                _member_view(m, users[m.user_id], viewer, can_manage)
                for m in by_participant.get(p.id, [])
            ),
        )
        for p in repository.participants(session, site_id)
    )
    return MembersView(
        site_id=site_id,
        site_name=site_name,
        my_role_label=ROLE_LABELS[my_role],
        can_manage=can_manage,
        participants=participants,
        role_options=tuple(RoleOption(r, ROLE_LABELS[r], r == role) for r in ALL_ROLES),
        email=email,
        errors=errors,
        message=message,
    )


def _member_view(
    membership: ProjectMembership, user: UserInfo, viewer: CurrentUser, can_manage: bool
) -> MemberView:
    return MemberView(
        membership_id=membership.id,
        display_name=user.display_name,
        email=user.email if can_manage else None,
        role_label=ROLE_LABELS[cast(Role, membership.role)],
        granted_text=f"{membership.created_at.astimezone(KST):%Y-%m-%d %H:%M}",
        is_me=user.user_id == viewer.user_id,
    )


def _membership(
    participant: ProjectParticipant,
    user_id: int,
    role: Role,
    granted_by: int | None,
    now: datetime,
) -> ProjectMembership:
    return ProjectMembership(
        site_id=participant.site_id,
        participant_id=participant.id,
        user_id=user_id,
        role=role,
        granted_by_user_id=granted_by,
        created_at=now,
    )
