"""공온 서비스 사이트(D-110, 슬랙 방식).

`/`는 로그인 전에는 첫 화면, 로그인 뒤에는 내 현장 고르기이고 현장을 고르면 PC 웹 앱(/home)으로
들어간다. 기능·소개·요금은 각자 페이지다. 앱 화면(휴대폰)은 서비스 사이트를 거치지 않는다:
로그인했으면 바로 앱 홈, 앱 껍데기에서 로그인 전이면 로그인으로 간다.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core import ui_mode
from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser
from app.features.sites import service as sites_service
from app.features.teams import service as teams_service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


def _visitor(request: Request, session: Session, now: datetime) -> CurrentUser | None:
    return auth_service.resolve(session, request.cookies.get(auth_service.SESSION_COOKIE), now)


@router.get("/", response_model=None)
def front(request: Request, session: SessionDep, now: NowDep) -> Response:
    user = _visitor(request, session, now)
    if user is not None and ui_mode.ui_mode(request) == "app":
        return RedirectResponse("/home", status_code=303)
    if user is None and ui_mode.in_app_shell(request.headers):
        return RedirectResponse("/login", status_code=303)
    if user is None:
        return templates.TemplateResponse(
            request, "intro/home.html", {"nav_active": "", "me_intro": None, "intro_page": "home"}
        )
    sites = sites_service.list_sites(session, teams_service.site_ids_for(session, user.user_id))
    context = {"nav_active": "", "me_intro": user, "intro_page": "launch", "sites": sites}
    return templates.TemplateResponse(request, "intro/launch.html", context)


def _page(request: Request, session: Session, now: datetime, name: str) -> HTMLResponse:
    context = {"nav_active": "", "me_intro": _visitor(request, session, now), "intro_page": name}
    return templates.TemplateResponse(request, f"intro/{name}.html", context)


@router.get("/features", response_class=HTMLResponse)
def features(request: Request, session: SessionDep, now: NowDep) -> HTMLResponse:
    return _page(request, session, now, "features")


@router.get("/about", response_class=HTMLResponse)
def about(request: Request, session: SessionDep, now: NowDep) -> HTMLResponse:
    return _page(request, session, now, "about")


@router.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request, session: SessionDep, now: NowDep) -> HTMLResponse:
    return _page(request, session, now, "pricing")


@router.get("/welcome")
def old_welcome() -> RedirectResponse:
    # 예전 환영 화면(D-072) 주소
    return RedirectResponse("/", status_code=308)
