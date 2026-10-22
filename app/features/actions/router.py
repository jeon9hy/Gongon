from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.params import OptionalSiteIdQuery
from app.core.templating import register_template_dir, templates
from app.features.actions import service
from app.features.auth.service import CurrentUserDep, require_user
from app.features.sites import service as sites_service
from app.features.teams import service as teams_service

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]

MESSAGES = {
    "delegated": "맡겼어요. 기간 안에는 그 사람이 대신 처리해요.",
    "revoked": "위임을 거뒀어요.",
}


def _page(
    request: Request,
    session: Session,
    user: CurrentUserDep,
    now: datetime,
    errors: tuple[str, ...] = (),
    message: str | None = None,
    status_code: int = 200,
    site_id: int | None = None,
) -> HTMLResponse:
    view = service.build_my_actions(session, user, now, errors, message)
    if site_id is not None:
        names = {
            s.site_id: s.name
            for s in sites_service.list_sites(
                session, teams_service.site_ids_for(session, user.user_id)
            )
        }
        if site_id in names:  # 참여하지 않은 현장 번호는 무시하고 전체를 보인다
            view = service.only_site(view, site_id, names[site_id])
    return templates.TemplateResponse(
        request, "actions/my.html", {"nav_active": "actions", "view": view}, status_code=status_code
    )


@router.get("/actions", response_class=HTMLResponse)
def my_actions(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    done: str = "",
    site_id: OptionalSiteIdQuery = None,
) -> HTMLResponse:
    return _page(request, session, user, now, message=MESSAGES.get(done), site_id=site_id)


@router.post("/actions/delegations")
def delegate(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    choice: Annotated[str, Form()] = "",
    start_date: Annotated[str, Form()] = "",
    start_time: Annotated[str, Form()] = "",
    end_date: Annotated[str, Form()] = "",
    end_time: Annotated[str, Form()] = "",
) -> Response:
    errors = service.add_delegation(
        session, user, choice, start_date, start_time, end_date, end_time, now
    )
    if errors:
        return _page(request, session, user, now, errors=errors, status_code=422)
    return RedirectResponse("/actions?done=delegated", status_code=303)


@router.post("/actions/delegations/{delegation_id}/revoke")
def revoke(
    request: Request, session: SessionDep, user: CurrentUserDep, now: NowDep, delegation_id: int
) -> Response:
    errors = service.revoke_delegation(session, user, delegation_id, now)
    if errors:
        return _page(request, session, user, now, errors=errors, status_code=409)
    return RedirectResponse("/actions?done=revoked", status_code=303)
