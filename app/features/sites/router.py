from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.sites import places, service
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
        work_start_date: Annotated[str, Form()] = "",
        work_end_date: Annotated[str, Form()] = "",
        work_types: Annotated[list[str] | None, Form()] = None,
    ) -> None:
        self.form = SiteForm(
            name=name,
            address=address,
            latitude=latitude,
            longitude=longitude,
            work_start=work_start,
            work_end=work_end,
            work_start_date=work_start_date,
            work_end_date=work_end_date,
            work_types=tuple(work_types or ()),
        )


FormDep = Annotated[_SiteFormFields, Depends()]


def _render(request: Request, view: SitesView, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "sites/index.html", {"nav_active": "sites", "view": view}, status_code=status_code
    )


@router.get("/sites", response_class=HTMLResponse)
def sites(
    request: Request,
    session: SessionDep,
    now: Annotated[datetime, Depends(now_kst)],
    site_id: int | None = None,
    saved: bool = False,
    deleted: bool = False,
) -> HTMLResponse:
    view = service.build_sites_view(
        session, site_id, saved=saved, today=now.date(), deleted=deleted
    )
    if view is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return _render(request, view)


@router.get("/sites/places")
def search_places(
    settings: Annotated[Settings, Depends(get_settings)],
    http_get: Annotated[places.HttpGetWithHeaders, Depends(places.get_place_http_get)],
    q: Annotated[str, Query(max_length=places.QUERY_MAX)] = "",
) -> JSONResponse:
    """현장 이름으로 장소 후보(주소·위경도)를 준다. 실패해도 직접 입력하도록 사유만 돌려준다."""
    query = q.strip()
    if len(query) < places.QUERY_MIN:
        return JSONResponse({"places": [], "message": None})
    try:
        found = places.search_places(query, settings.kakao_rest_api_key, http_get)
    except places.PlaceSearchError as error:
        places.logger.warning("장소 검색 실패 q=%r: %s", query, error)
        return JSONResponse({"places": [], "message": f"장소 검색 실패 · {error}"})
    message = None if found else _NO_PLACE_MESSAGE
    return JSONResponse({"places": [p.to_json() for p in found], "message": message})


_NO_PLACE_MESSAGE = "검색 결과가 없습니다. 다른 이름으로 찾거나 위도·경도를 직접 입력하세요."


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


@router.post("/sites/{site_id}/delete")
def delete_site(
    session: SessionDep, now: Annotated[datetime, Depends(now_kst)], site_id: int
) -> RedirectResponse:
    if not service.delete_site(session, site_id, now):
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return RedirectResponse("/sites?deleted=true", status_code=303)
