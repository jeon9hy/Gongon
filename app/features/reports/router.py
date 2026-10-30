from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.reports import service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


@router.get("/reports/{site_id}/weekly", response_class=HTMLResponse)
def weekly(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    site_id: int,
    start: str = "",
) -> HTMLResponse:
    """주간 작업계획표(C14-1, D-112). 날짜가 잘못되면 기본(다음 주)을 보인다."""
    view = service.build_weekly(session, user, site_id, now, _date(start))
    return templates.TemplateResponse(
        request, "reports/weekly.html", {"nav_active": "", "view": view}
    )


def _date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None
