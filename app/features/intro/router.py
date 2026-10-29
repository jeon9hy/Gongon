"""서비스 소개이자 PC 웹 입구(D-110, 슬랙 방식). 로그인과 관계없이 `/`는 소개이고,
로그인했으면 소개 첫 화면에서 내 현장을 골라 PC 웹 앱(/home)으로 들어간다.
앱 화면(휴대폰)은 소개 없이 바로 앱 홈, 앱 껍데기에서 로그인 전이면 로그인으로 간다."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core import ui_mode
from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth import service as auth_service
from app.features.sites import service as sites_service
from app.features.teams import service as teams_service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)


@router.get("/", response_model=None)
def intro(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    now: Annotated[datetime, Depends(now_kst)],
) -> Response:
    user = auth_service.resolve(session, request.cookies.get(auth_service.SESSION_COOKIE), now)
    if user is not None and ui_mode.ui_mode(request) == "app":
        return RedirectResponse("/home", status_code=303)
    if user is None and ui_mode.in_app_shell(request.headers):
        return RedirectResponse("/login", status_code=303)
    sites = (
        sites_service.list_sites(session, teams_service.site_ids_for(session, user.user_id))
        if user is not None
        else ()
    )
    context = {"nav_active": "", "me_intro": user, "sites": sites}
    return templates.TemplateResponse(request, "intro/intro.html", context)


@router.get("/welcome")
@router.get("/about")
def old_intro_address() -> RedirectResponse:
    # 예전 환영(D-072)·소개(C04-20) 주소는 합친 소개로 보낸다
    return RedirectResponse("/", status_code=308)
