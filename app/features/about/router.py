"""공온 소개 페이지(개발자 요청 2026-10-17). 로그인 없이 열리는 회사 소개 화면이다."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth import service as auth_service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)


@router.get("/about", response_class=HTMLResponse)
def about(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    now: Annotated[datetime, Depends(now_kst)],
) -> HTMLResponse:
    user = auth_service.resolve(session, request.cookies.get(auth_service.SESSION_COOKIE), now)
    return templates.TemplateResponse(
        request, "about/about.html", {"nav_active": "about", "signed_in": user is not None}
    )
