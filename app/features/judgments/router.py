from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.forecasts import service as forecasts_service
from app.features.judgments import service
from app.features.judgments.schemas import ElementKey, RunResult, VerdictFilter
from engine.forecast import HttpGet

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request, session: SessionDep, now: NowDep, ran: RunResult | None = None
) -> HTMLResponse:
    view = service.build_home(session, now, ran)
    return templates.TemplateResponse(
        request, "judgments/home.html", {"nav_active": "home", "view": view}
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: SessionDep,
    now: NowDep,
    site_id: int | None = None,
    element: ElementKey | None = None,
    hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    ran: RunResult | None = None,
    work: Annotated[str | None, Query(max_length=60)] = None,
) -> HTMLResponse:
    view = service.build_dashboard(session, site_id, element, hour, now, ran, work)
    if view is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return templates.TemplateResponse(
        request, "judgments/dashboard.html", {"nav_active": "dashboard", "view": view}
    )


@router.post("/judgments/run")
def run(
    session: SessionDep,
    now: NowDep,
    settings: Annotated[Settings, Depends(get_settings)],
    http_get: Annotated[HttpGet, Depends(forecasts_service.get_http_get)],
    site_id: Annotated[int, Form()],
) -> RedirectResponse:
    result = service.run_for_site(
        session, site_id, now, settings.kma_auth(), http_get, settings.kma_service_key
    )
    if result is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    # 새로고침해도 다시 실행되지 않도록 결과는 GET으로 보여준다.
    return RedirectResponse(service.dashboard_href(site_id, ran=result), status_code=303)


@router.post("/judgments/run-all")
def run_all(
    session: SessionDep,
    now: NowDep,
    settings: Annotated[Settings, Depends(get_settings)],
    http_get: Annotated[HttpGet, Depends(forecasts_service.get_http_get)],
) -> RedirectResponse:
    result = service.run_all(session, now, settings.kma_auth(), http_get, settings.kma_service_key)
    return RedirectResponse(f"/?ran={result}", status_code=303)


@router.get("/judgments", response_class=HTMLResponse)
def history(
    request: Request,
    session: SessionDep,
    verdict: VerdictFilter = "전체",
    site_id: int | None = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
) -> HTMLResponse:
    view = service.build_history(session, verdict, site_id, page)
    return templates.TemplateResponse(
        request, "judgments/history.html", {"nav_active": "history", "view": view}
    )


@router.get("/judgments/{judgment_id}", response_class=HTMLResponse)
def detail(request: Request, session: SessionDep, judgment_id: int) -> HTMLResponse:
    view = service.get_detail(session, judgment_id)
    if view is None:
        raise HTTPException(status_code=404, detail="판정 내역을 찾을 수 없습니다")
    return templates.TemplateResponse(
        request, "judgments/detail.html", {"nav_active": "history", "view": view}
    )
