from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.chat import service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


@router.get("/chat", response_model=None)
def chat_home(request: Request, session: SessionDep, user: CurrentUserDep) -> Response:
    """참여 중인 첫 현장 방으로 보낸다. 현장이 없으면 빈 화면."""
    choices = service.rooms(session, user)
    if choices:
        return RedirectResponse(f"/chat/{choices[0].site_id}", status_code=303)
    return templates.TemplateResponse(
        request, "chat/room.html", {"nav_active": "chat", "view": None}
    )


@router.get("/chat/{site_id}", response_class=HTMLResponse)
def room(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    site_id: int,
    before: int | None = None,
) -> HTMLResponse:
    view = service.build_room(session, user, site_id, before_id=before)
    return templates.TemplateResponse(
        request, "chat/room.html", {"nav_active": "chat", "view": view}
    )


@router.get("/chat/{site_id}/messages", response_class=HTMLResponse)
def poll(
    request: Request, session: SessionDep, user: CurrentUserDep, site_id: int, after: int = 0
) -> HTMLResponse:
    """after 뒤의 새 메시지 조각(화면이 짧은 주기로 부른다)."""
    messages = service.new_messages(session, user, site_id, after)
    return templates.TemplateResponse(
        request, "chat/_messages.html", {"messages": messages, "site_id": site_id}
    )


@router.post("/chat/{site_id}/messages")
def send(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    site_id: int,
    body: Annotated[str, Form()] = "",
    case_id: Annotated[str, Form()] = "",
) -> Response:
    errors = service.post(session, user, site_id, body, case_id, now)
    if errors:
        view = service.build_room(session, user, site_id, errors=errors, draft=body)
        return templates.TemplateResponse(
            request, "chat/room.html", {"nav_active": "chat", "view": view}, status_code=422
        )
    return RedirectResponse(f"/chat/{site_id}#end", status_code=303)


@router.post("/chat/{site_id}/messages/{message_id}/delete")
def delete(
    session: SessionDep, user: CurrentUserDep, now: NowDep, site_id: int, message_id: int
) -> RedirectResponse:
    service.delete(session, user, site_id, message_id, now)
    return RedirectResponse(f"/chat/{site_id}#end", status_code=303)
