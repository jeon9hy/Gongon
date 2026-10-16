from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.teams.models import ParticipantContact, ProjectMembership, ProjectParticipant


def active_site_ids(session: Session, user_id: int, roles: tuple[str, ...]) -> frozenset[int]:
    query = select(ProjectMembership.site_id).where(
        ProjectMembership.user_id == user_id,
        ProjectMembership.revoked_at.is_(None),
        ProjectMembership.role.in_(roles),
    )
    return frozenset(session.scalars(query))


def active_membership(session: Session, user_id: int, site_id: int) -> ProjectMembership | None:
    return session.scalar(
        select(ProjectMembership).where(
            ProjectMembership.user_id == user_id,
            ProjectMembership.site_id == site_id,
            ProjectMembership.revoked_at.is_(None),
        )
    )


def participants(session: Session, site_id: int) -> list[ProjectParticipant]:
    query = (
        select(ProjectParticipant)
        .where(ProjectParticipant.site_id == site_id)
        # 원청을 먼저 보인다
        .order_by(ProjectParticipant.kind, ProjectParticipant.id)
    )
    return list(session.scalars(query))


def participants_for_sites(session: Session, site_ids: list[int]) -> list[ProjectParticipant]:
    query = select(ProjectParticipant).where(ProjectParticipant.site_id.in_(site_ids))
    return list(session.scalars(query))


def participant_of(
    session: Session, site_id: int, organization_id: int
) -> ProjectParticipant | None:
    return session.scalar(
        select(ProjectParticipant).where(
            ProjectParticipant.site_id == site_id,
            ProjectParticipant.organization_id == organization_id,
        )
    )


def active_memberships(session: Session, site_id: int) -> list[ProjectMembership]:
    query = (
        select(ProjectMembership)
        .where(ProjectMembership.site_id == site_id, ProjectMembership.revoked_at.is_(None))
        .order_by(ProjectMembership.id)
    )
    return list(session.scalars(query))


def lock_active_coordinators(session: Session, site_id: int) -> list[ProjectMembership]:
    """마지막 조정자 회수 검사용. 동시에 서로를 회수해 조정자가 0명이 되지 않게 잠근다."""
    query = (
        select(ProjectMembership)
        .where(
            ProjectMembership.site_id == site_id,
            ProjectMembership.revoked_at.is_(None),
            ProjectMembership.role == "coordinator",
        )
        .with_for_update()
    )
    return list(session.scalars(query))


def participant(session: Session, site_id: int, participant_id: int) -> ProjectParticipant | None:
    found = session.get(ProjectParticipant, participant_id)
    return found if found is not None and found.site_id == site_id else None


def organization_has_participants(session: Session, organization_id: int) -> bool:
    query = select(ProjectParticipant.id).where(
        ProjectParticipant.organization_id == organization_id
    )
    return session.scalar(query.limit(1)) is not None


def contacts(session: Session, site_id: int) -> list[ParticipantContact]:
    query = (
        select(ParticipantContact)
        .where(ParticipantContact.site_id == site_id, ParticipantContact.removed_at.is_(None))
        .order_by(ParticipantContact.participant_id, ParticipantContact.id)
    )
    return list(session.scalars(query))


def contact(session: Session, site_id: int, contact_id: int) -> ParticipantContact | None:
    found = session.get(ParticipantContact, contact_id)
    if found is None or found.site_id != site_id or found.removed_at is not None:
        return None
    return found


def user_has_contact_links(session: Session, user_id: int) -> bool:
    query = select(ParticipantContact.id).where(
        ParticipantContact.user_id == user_id, ParticipantContact.removed_at.is_(None)
    )
    return session.scalar(query.limit(1)) is not None
