from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.board import service
from app.features.teams import service as teams_service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


@router.get("/board", response_model=None)
def board_home(session: SessionDep, user: CurrentUserDep) -> Response:
    """게시 계정이 로그인하면 그 현장 게시 화면으로 간다."""
    sites = sorted(teams_service.board_site_ids(session, user.user_id))
    if not sites:
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(f"/board/{sites[0]}", status_code=303)


@router.get("/board/{site_id}", response_class=HTMLResponse)
def board(
    request: Request, session: SessionDep, user: CurrentUserDep, now: NowDep, site_id: int
) -> HTMLResponse:
    view = service.build_board(session, user, site_id, now)
    return templates.TemplateResponse(request, "board/board.html", {"nav_active": "", "view": view})
