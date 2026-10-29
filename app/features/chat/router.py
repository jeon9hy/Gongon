from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.files import FileStoreDep
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.chat import service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


@router.get("/chat", response_model=None)
def chat_home(request: Request, session: SessionDep, user: CurrentUserDep, now: NowDep) -> Response:
    """방을 미리 고르지 않는다(C04-36): 참여 현장 방 목록만 보이는 화면. 최근 대화한 방부터."""
    return templates.TemplateResponse(
        request,
        "chat/room.html",
        {"nav_active": "chat", "view": None, "rooms": service.room_list(session, user, now)},
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
    store: FileStoreDep,
    body: Annotated[str, Form()] = "",
    case_id: Annotated[str, Form()] = "",
    contact_id: Annotated[str, Form()] = "",
    action_id: Annotated[str, Form()] = "",
    photo: Annotated[UploadFile | None, File()] = None,
) -> Response:
    # 한도보다 1바이트 더 읽어 넘치는지만 본다(큰 파일을 끝까지 메모리에 올리지 않는다)
    data = photo.file.read(service.PHOTO_MAX_BYTES + 1) if photo and photo.filename else None
    attach = {"case_id": case_id, "contact_id": contact_id, "action_id": action_id}
    errors = service.post(session, user, site_id, body, attach, data, store, now)
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


@router.get("/chat/{site_id}/photos/{message_id}")
def photo(
    session: SessionDep, user: CurrentUserDep, store: FileStoreDep, site_id: int, message_id: int
) -> FileResponse:
    """대화방 사진(D-111). 그 현장 참여자만. 공용 캐시에 남기지 않는다."""
    path, media_type = service.photo_file(session, user, site_id, message_id, store)
    return FileResponse(
        path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"}
    )
