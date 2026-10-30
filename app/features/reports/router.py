from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.reports import service
from app.features.reports.schemas import ChangeDocKind, ReportForm

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


@router.get("/reports/{site_id}/daily", response_class=HTMLResponse)
def daily(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    site_id: int,
    day: str = "",
) -> HTMLResponse:
    """작업일보·공사일보(C14-2, D-112). 날짜가 잘못되면 오늘을 보인다."""
    view = service.build_daily(session, user, site_id, now, _date(day))
    return templates.TemplateResponse(
        request, "reports/daily.html", {"nav_active": "", "view": view}
    )


@router.post("/reports/{site_id}/daily/{item_id}", response_model=None)
def save_daily(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    site_id: int,
    item_id: int,
    outcome: Annotated[str, Form()] = "",
    causes: Annotated[list[str] | None, Form()] = None,
    workers: Annotated[str, Form()] = "",
    equipment_note: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    known_when: Annotated[str, Form()] = "",
) -> Response:
    form = ReportForm(outcome=outcome, causes=tuple(causes or ()), workers=workers,
                      equipment_note=equipment_note, note=note, known_when=known_when)  # fmt: skip
    work_date, errors = service.save_report(session, user, site_id, item_id, form, now)
    if errors:
        view = service.build_daily(session, user, site_id, now, work_date, errors, item_id, form)
        return templates.TemplateResponse(
            request, "reports/daily.html", {"nav_active": "", "view": view}, status_code=422
        )
    return RedirectResponse(
        f"/reports/{site_id}/daily?day={work_date.isoformat()}#work-{item_id}", status_code=303
    )


@router.get("/reports/{site_id}/weather", response_class=HTMLResponse)
def weather_log(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    site_id: int,
    month: str = "",
) -> HTMLResponse:
    """기상 작업중지 기록(C14-3, D-112). 달이 잘못되면 이번 달을 보인다."""
    view = service.build_weather_log(session, user, site_id, now, month)
    return templates.TemplateResponse(
        request, "reports/weather.html", {"nav_active": "", "view": view}
    )


@router.get("/reports/{site_id}/changes/{case_id}", response_class=HTMLResponse)
def change_doc(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    site_id: int,
    case_id: int,
    kind: str = "order",
) -> HTMLResponse:
    """변경 건 문서(C14-4, D-112): kind=order 작업 지시서, kind=report 실정보고 초안."""
    doc_kind: ChangeDocKind = "report" if kind == "report" else "order"
    view = service.build_change_doc(session, user, site_id, case_id, doc_kind, now)
    return templates.TemplateResponse(
        request, "reports/change_doc.html", {"nav_active": "", "view": view}
    )


@router.get("/reports/{site_id}/losses", response_class=HTMLResponse)
def losses(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    site_id: int,
    month: str = "",
) -> HTMLResponse:
    """작업 차질 월 집계(C14-5, D-113). 달이 잘못되면 이번 달을 보인다."""
    view = service.build_loss_summary(session, user, site_id, now, month)
    return templates.TemplateResponse(
        request, "reports/losses.html", {"nav_active": "", "view": view}
    )


def _date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None
