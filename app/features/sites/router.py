from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.sites import service
from app.features.sites.schemas import SiteForm, SitesView

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]


class _SiteFormFields:
    """HTML 폼 필드 → SiteForm. 체크박스 work_types는 여러 값으로 온다."""

    def __init__(
        self,
        name: Annotated[str, Form()] = "",
        address: Annotated[str, Form()] = "",
        latitude: Annotated[str, Form()] = "",
        longitude: Annotated[str, Form()] = "",
        work_start: Annotated[str, Form()] = "",
        work_end: Annotated[str, Form()] = "",
        work_types: Annotated[list[str] | None, Form()] = None,
    ) -> None:
        self.form = SiteForm(
            name=name,
            address=address,
            latitude=latitude,
            longitude=longitude,
            work_start=work_start,
            work_end=work_end,
            work_types=tuple(work_types or ()),
        )


FormDep = Annotated[_SiteFormFields, Depends()]


def _render(request: Request, view: SitesView, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "sites/index.html", {"nav_active": "sites", "view": view}, status_code=status_code
    )


@router.get("/sites", response_class=HTMLResponse)
def sites(
    request: Request, session: SessionDep, site_id: int | None = None, saved: bool = False
) -> HTMLResponse:
    view = service.build_sites_view(session, site_id, saved=saved)
    if view is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return _render(request, view)


@router.post("/sites")
def create_site(request: Request, session: SessionDep, fields: FormDep) -> Response:
    site_id, errors = service.create_site(session, fields.form)
    if site_id is None:
        view = service.build_sites_view(session, None, fields.form, errors)
        assert view is not None
        return _render(request, view, status_code=422)
    return RedirectResponse(f"/sites?site_id={site_id}&saved=true", status_code=303)


@router.post("/sites/{site_id}")
def update_site(request: Request, session: SessionDep, site_id: int, fields: FormDep) -> Response:
    found, errors = service.update_site(session, site_id, fields.form)
    if not found:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    if errors:
        view = service.build_sites_view(session, site_id, fields.form, errors)
        assert view is not None
        return _render(request, view, status_code=422)
    return RedirectResponse(f"/sites?site_id={site_id}&saved=true", status_code=303)
