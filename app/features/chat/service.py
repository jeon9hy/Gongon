"""현장 대화방(C12, D-071).

- 현장마다 방 하나. 활성 멤버십이 있는 사람만 읽고 쓴다. 비참여 현장은 404(teams 서비스).
- 메시지는 지우지 않고 숨긴다(작성자만). 메시지가 조치·변경 상태를 바꾸지 않는다.
- 관련 변경 건 카드는 저장한 글이 아니라 지금 상태를 읽어 보인다.
- 새 메시지는 짧은 주기로 불러온다(after_id 이후만, 실시간 연결은 필요가 확인될 때).
"""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser
from app.features.changes import service as changes_service
from app.features.chat.models import SiteMessage
from app.features.chat.schemas import ChatView, MessageView, RoomChoice
from app.features.sites import service as sites_service
from app.features.teams import service as teams_service
from app.features.teams.schemas import ALL_ROLES
from engine.kst import KST

BODY_MAX = 1000
PAGE = 50
_WEEKDAYS = "월화수목금토일"


def rooms(session: Session, user: CurrentUser) -> tuple[RoomChoice, ...]:
    site_ids = teams_service.site_ids_for(session, user.user_id)
    return tuple(
        RoomChoice(s.site_id, s.name, False) for s in sites_service.list_sites(session, site_ids)
    )


def build_room(
    session: Session,
    user: CurrentUser,
    site_id: int,
    errors: tuple[str, ...] = (),
    draft: str = "",
    before_id: int | None = None,
) -> ChatView:
    teams_service.require_role(session, user, site_id, ALL_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    query = select(SiteMessage).where(SiteMessage.site_id == site_id)
    if before_id is not None:
        query = query.where(SiteMessage.id < before_id)
    recent = list(session.scalars(query.order_by(SiteMessage.id.desc()).limit(PAGE + 1)))
    has_older = len(recent) > PAGE
    shown = list(reversed(recent[:PAGE]))
    return ChatView(
        site_id=site_id,
        site_name=site.name,
        rooms=tuple(
            RoomChoice(r.site_id, r.name, r.site_id == site_id) for r in rooms(session, user)
        ),
        messages=_views(session, user, site_id, shown),
        last_id=shown[-1].id if shown else 0,
        has_older=has_older,
        case_choices=changes_service.case_choices(session, site_id),
        can_write=True,
        errors=errors,
        draft=draft,
    )


def new_messages(
    session: Session, user: CurrentUser, site_id: int, after_id: int
) -> tuple[MessageView, ...]:
    """after_id 뒤의 메시지(불러오기). 한 번에 PAGE건까지."""
    teams_service.require_role(session, user, site_id, ALL_ROLES)
    rows = list(
        session.scalars(
            select(SiteMessage)
            .where(SiteMessage.site_id == site_id, SiteMessage.id > after_id)
            .order_by(SiteMessage.id)
            .limit(PAGE)
        )
    )
    return _views(session, user, site_id, rows)


def post(
    session: Session, user: CurrentUser, site_id: int, body: str, case_id: str, now: datetime
) -> tuple[str, ...]:
    teams_service.require_role(session, user, site_id, ALL_ROLES)
    text = body.strip()
    if not text:
        return ("메시지를 입력해 주세요.",)
    if len(text) > BODY_MAX:
        return (f"메시지는 {BODY_MAX}자까지 보낼 수 있어요.",)
    linked = None
    if case_id:
        linked = int(case_id) if case_id.isdigit() else -1
        if linked not in changes_service.case_cards(session, site_id, [linked]):
            return ("이 현장의 변경 건을 골라 주세요.",)
    session.add(
        SiteMessage(
            site_id=site_id,
            author_user_id=user.user_id,
            body=text,
            linked_case_id=linked,
            created_at=now,
        )
    )
    session.commit()
    return ()


def delete(
    session: Session, user: CurrentUser, site_id: int, message_id: int, now: datetime
) -> None:
    """작성자만 숨긴다. 행과 연결은 남긴다(기록 보존)."""
    teams_service.require_role(session, user, site_id, ALL_ROLES)
    message = session.get(SiteMessage, message_id)
    if message is None or message.site_id != site_id:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    if message.author_user_id != user.user_id:
        raise HTTPException(status_code=403, detail=teams_service.FORBIDDEN)
    if message.deleted_at is None:
        message.deleted_at = now
        session.commit()


def _views(
    session: Session, user: CurrentUser, site_id: int, rows: list[SiteMessage]
) -> tuple[MessageView, ...]:
    people = auth_service.describe_users(session, {m.author_user_id for m in rows})
    cards = changes_service.case_cards(
        session, site_id, [m.linked_case_id for m in rows if m.linked_case_id is not None]
    )
    views = []
    for m in rows:
        info = people.get(m.author_user_id)
        local = m.created_at.astimezone(KST)
        deleted = m.deleted_at is not None
        views.append(
            MessageView(
                message_id=m.id,
                author_name="알 수 없음" if info is None else info.display_name,
                author_company="" if info is None else info.organization_name,
                mine=m.author_user_id == user.user_id,
                body=None if deleted else m.body,
                time_text=f"{local:%H:%M}",
                day_text=f"{local.month}월 {local.day}일({_WEEKDAYS[local.weekday()]})",
                case=None if deleted or m.linked_case_id is None else cards.get(m.linked_case_id),
                can_delete=not deleted and m.author_user_id == user.user_id,
            )
        )
    return tuple(views)
