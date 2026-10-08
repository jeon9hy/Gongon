from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.schedules import service
from app.features.schedules.schemas import ScheduleView, WorkItemForm

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


def _render(request: Request, view: ScheduleView, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "schedules/index.html",
        {"nav_active": "schedule", "view": view},
        status_code=status_code,
    )


@router.get("/schedule", response_class=HTMLResponse)
def schedule(
    request: Request,
    session: SessionDep,
    now: NowDep,
    site_id: int | None = None,
    saved: bool = False,
    deleted: bool = False,
) -> HTMLResponse:
    message = "작업을 추가했습니다." if saved else "작업을 지웠습니다." if deleted else None
    view = service.build_view(session, site_id, now.date(), message=message)
    if view is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return _render(request, view)


@router.post("/schedule")
def add_item(
    request: Request,
    session: SessionDep,
    now: NowDep,
    site_id: Annotated[int, Form()],
    work_type: Annotated[str, Form()] = "",
    work_date: Annotated[str, Form()] = "",
    start: Annotated[str, Form()] = "",
    end: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    memo: Annotated[str, Form()] = "",
) -> Response:
    form = WorkItemForm(work_type, work_date, start, end, location, memo)
    ok, errors = service.add_item(session, site_id, form, now.date())
    if not ok:
        view = service.build_view(session, site_id, now.date(), form, errors)
        if view is None:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
        return _render(request, view, status_code=422)
    return RedirectResponse(f"/schedule?site_id={site_id}&saved=1", status_code=303)


@router.post("/schedule/{item_id}/delete")
def delete_item(
    session: SessionDep, item_id: int, site_id: Annotated[int, Form()]
) -> RedirectResponse:
    if not service.delete_item(session, site_id, item_id):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    return RedirectResponse(f"/schedule?site_id={site_id}&deleted=1", status_code=303)
