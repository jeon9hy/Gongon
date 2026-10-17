from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.forecasts import service as forecasts_service
from app.features.judgments import service
from app.features.judgments.schemas import ElementKey, RunResult, VerdictFilter
from app.features.teams import service as teams_service
from app.features.teams.service import AccessibleSitesDep, ManagedSitesDep
from engine.forecast import HttpGet

register_template_dir(Path(__file__).parent / "templates")

# 모든 화면은 로그인이 필요하다(D-057).
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


@router.get("/", response_model=None)
def home(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    manageable: ManagedSitesDep,
    now: NowDep,
    ran: RunResult | None = None,
    site_id: int | None = None,
) -> Response:
    if not scope and teams_service.board_site_ids(session, user.user_id):
        return RedirectResponse("/board", status_code=303)  # 현장 TV 계정은 게시 화면만(D-067)
    view = service.build_home(session, scope, now, ran, site_id)
    return templates.TemplateResponse(
        request,
        "judgments/home.html",
        {"nav_active": "home", "view": view, "manageable": manageable},
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: SessionDep,
    scope: AccessibleSitesDep,
    manageable: ManagedSitesDep,
    now: NowDep,
    site_id: int | None = None,
    element: ElementKey | None = None,
    hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    ran: RunResult | None = None,
    work: Annotated[str | None, Query(max_length=60)] = None,
) -> HTMLResponse:
    if site_id is None and scope is not None and len(scope) > 1:
        # 현장을 고르지 않고 들어오면 전체 현장 요약(개발자 요청 2026-10-17)
        overview = service.build_home(session, scope, now, ran)
        return templates.TemplateResponse(
            request,
            "judgments/dashboard_all.html",
            {"nav_active": "dashboard", "view": overview, "manageable": manageable},
        )
    view = service.build_dashboard(session, scope, site_id, element, hour, now, ran, work)
    if view is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return templates.TemplateResponse(
        request,
        "judgments/dashboard.html",
        {"nav_active": "dashboard", "view": view, "manageable": manageable},
    )


@router.post("/judgments/run")
def run(
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    settings: Annotated[Settings, Depends(get_settings)],
    http_get: Annotated[HttpGet, Depends(forecasts_service.get_http_get)],
    site_id: Annotated[int, Form()],
) -> RedirectResponse:
    result = service.run_for_user_site(
        session, user, site_id, now, settings.kma_auth(), http_get, settings.kma_service_key
    )
    if result is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    # 새로고침해도 다시 실행되지 않도록 결과는 GET으로 보여준다.
    return RedirectResponse(service.dashboard_href(site_id, ran=result), status_code=303)


@router.post("/judgments/run-all")
def run_all(
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    settings: Annotated[Settings, Depends(get_settings)],
    http_get: Annotated[HttpGet, Depends(forecasts_service.get_http_get)],
) -> RedirectResponse:
    # 화면의 전체 판정은 내가 조정자인 현장만 한다(D-057).
    scope = teams_service.managed_site_ids(session, user.user_id)
    result = service.run_all(
        session, scope, now, settings.kma_auth(), http_get, settings.kma_service_key
    )
    return RedirectResponse(f"/?ran={result}", status_code=303)


@router.get("/judgments", response_class=HTMLResponse)
def history(
    request: Request,
    session: SessionDep,
    scope: AccessibleSitesDep,
    verdict: VerdictFilter = "전체",
    site_id: int | None = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    size: int = service.HISTORY_PAGE_SIZES[0],
) -> HTMLResponse:
    if size not in service.HISTORY_PAGE_SIZES:
        raise HTTPException(status_code=422, detail=f"size는 {service.HISTORY_PAGE_SIZES} 중 하나")
    view = service.build_history(session, scope, verdict, site_id, page, size)
    return templates.TemplateResponse(
        request, "judgments/history.html", {"nav_active": "history", "view": view}
    )


@router.get("/judgments/{judgment_id}", response_class=HTMLResponse)
def detail(
    request: Request, session: SessionDep, scope: AccessibleSitesDep, judgment_id: int
) -> HTMLResponse:
    view = service.get_detail(session, scope, judgment_id)
    if view is None:
        raise HTTPException(status_code=404, detail="판정 내역을 찾을 수 없습니다")
    return templates.TemplateResponse(
        request, "judgments/detail.html", {"nav_active": "history", "view": view}
    )
