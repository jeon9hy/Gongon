from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.sites import service as sites_service
from app.features.teams import service
from app.features.teams.schemas import MembersView
from app.features.teams.service import AccessibleSitesDep

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


def _site_name(session: Session, site_id: int, scope: frozenset[int]) -> str:
    site = sites_service.get_site(session, site_id, scope)
    if site is None:
        raise HTTPException(status_code=404, detail=service.NOT_FOUND)
    return site.name


def _render(request: Request, view: MembersView, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "teams/members.html",
        {"nav_active": "sites", "view": view},
        status_code=status_code,
    )


@router.get("/sites/{site_id}/members", response_class=HTMLResponse)
def members(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    site_id: int,
    added: bool = False,
    revoked: bool = False,
) -> HTMLResponse:
    message = "참여자를 추가했습니다." if added else "권한을 회수했습니다." if revoked else None
    name = _site_name(session, site_id, scope)
    return _render(
        request, service.build_members_view(session, site_id, name, user, message=message)
    )


@router.post("/sites/{site_id}/members")
def add_member(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    now: NowDep,
    site_id: int,
    email: Annotated[str, Form()] = "",
    role: Annotated[str, Form()] = "",
) -> Response:
    name = _site_name(session, site_id, scope)
    errors = service.add_member(session, site_id, user, email, role, now)
    if errors:
        view = service.build_members_view(
            session, site_id, name, user, email=email.strip(), role=role, errors=errors
        )
        return _render(request, view, status_code=422)
    return RedirectResponse(f"/sites/{site_id}/members?added=true", status_code=303)


@router.post("/sites/{site_id}/members/{membership_id}/revoke")
def revoke_member(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    now: NowDep,
    site_id: int,
    membership_id: int,
) -> Response:
    name = _site_name(session, site_id, scope)
    errors = service.revoke_member(session, site_id, user, membership_id, now)
    if errors:
        view = service.build_members_view(session, site_id, name, user, errors=errors)
        return _render(request, view, status_code=422)
    if service.role_on(session, user.user_id, site_id) is None:
        # 자기 권한을 회수했으면 이 현장은 더 볼 수 없다
        return RedirectResponse("/sites", status_code=303)
    return RedirectResponse(f"/sites/{site_id}/members?revoked=true", status_code=303)
