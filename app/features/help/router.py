"""공온 가이드·내 정보(C04-7, D-064). 화면 곳곳의 설명 문장은 여기로 모으고 화면은 짧게 둔다."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser
from app.features.auth.service import CurrentUserDep, require_user
from app.features.sites import service as sites_service
from app.features.teams import service as teams_service
from app.features.teams.schemas import ROLE_LABELS, Role

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]


@dataclass(frozen=True, slots=True)
class MySite:
    name: str
    href: str
    role_label: str


@router.get("/guide", response_class=HTMLResponse)
def guide(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "help/guide.html", {"nav_active": "guide"})


@router.get("/me", response_class=HTMLResponse)
def me(request: Request, session: SessionDep, user: CurrentUserDep, done: str = "") -> HTMLResponse:
    message = "휴대폰 번호를 저장했어요." if done == "phone" else None
    return _me_page(request, session, user, message=message)


@router.post("/me/phone", response_model=None)
def save_phone(
    request: Request, session: SessionDep, user: CurrentUserDep, phone: Annotated[str, Form()] = ""
) -> Response:
    errors = auth_service.set_phone(session, user.user_id, phone)
    if errors:
        return _me_page(request, session, user, errors=errors, phone_input=phone, status_code=422)
    return RedirectResponse("/me?done=phone", status_code=303)


def _me_page(
    request: Request,
    session: Session,
    user: CurrentUser,
    message: str | None = None,
    errors: tuple[str, ...] = (),
    phone_input: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    # 현장 수만큼 역할을 읽는다(한 사람이 참여하는 현장은 많지 않다)
    site_ids = teams_service.site_ids_for(session, user.user_id)
    sites = tuple(
        MySite(
            name=s.name,
            href=f"/sites?site_id={s.site_id}",
            role_label=ROLE_LABELS[
                cast(Role, teams_service.role_on(session, user.user_id, s.site_id))
            ],
        )
        for s in sites_service.list_sites(session, site_ids)
    )
    info = auth_service.describe_users(session, [user.user_id]).get(user.user_id)
    phone = auth_service.format_phone(None if info is None else info.phone)
    context = {
        "nav_active": "me",
        "user": user,
        "sites": sites,
        "phone": phone,
        "phone_input": phone if phone_input is None else phone_input,
        "message": message,
        "errors": errors,
    }
    return templates.TemplateResponse(request, "help/me.html", context, status_code=status_code)
