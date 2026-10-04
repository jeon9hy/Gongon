from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core.templating import register_template_dir, templates
from app.features.sites import service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)


@router.get("/sites", response_class=HTMLResponse)
def sites(request: Request, site_id: int | None = None) -> HTMLResponse:
    view = service.build_sites_view(service.first_site_id() if site_id is None else site_id)
    if view is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return templates.TemplateResponse(
        request, "sites/index.html", {"nav_active": "sites", "view": view}
    )
