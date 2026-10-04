from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.core.templating import register_template_dir, templates
from app.features.judgments import sample, service
from app.features.judgments.schemas import Element, VerdictFilter

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)

_FIRST_HOUR = sample.HOURS[0]
_LAST_HOUR = sample.HOURS[-1]
_DEFAULT_HOUR = 15


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    element: Element = "rain",
    hour: Annotated[int, Query(ge=_FIRST_HOUR, le=_LAST_HOUR)] = _DEFAULT_HOUR,
) -> HTMLResponse:
    view = service.build_dashboard(element, hour)
    return templates.TemplateResponse(
        request, "judgments/dashboard.html", {"nav_active": "dashboard", "view": view}
    )


@router.get("/judgments", response_class=HTMLResponse)
def history(
    request: Request, verdict: VerdictFilter = "전체", site: str = service.ALL_SITES
) -> HTMLResponse:
    view = service.build_history(verdict, site)
    return templates.TemplateResponse(
        request, "judgments/history.html", {"nav_active": "history", "view": view}
    )


@router.get("/judgments/{judgment_id}", response_class=HTMLResponse)
def detail(request: Request, judgment_id: int) -> HTMLResponse:
    view = service.get_detail(judgment_id)
    if view is None:
        raise HTTPException(status_code=404, detail="판정 내역을 찾을 수 없습니다")
    return templates.TemplateResponse(
        request, "judgments/detail.html", {"nav_active": "dashboard", "view": view}
    )
