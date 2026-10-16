from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.changes import service
from app.features.changes.schemas import ChangeDetailView, ChangeForm, ChangeFormView
from app.features.teams.service import AccessibleSitesDep

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]

MESSAGES = {
    "proposed": "변경을 제안했습니다.",
    "submitted": "영향 검토로 보냈습니다. 조정자가 확인한 뒤 확정합니다.",
    "confirmed": "변경을 확정했습니다. 작업 계획이 바뀌었습니다. 바뀐 시간으로 다시 판정하세요.",
    "already": "이미 확정된 요청입니다. 다시 저장하지 않았습니다.",
    "withdrawn": "제안을 철회했습니다.",
}


def _form_page(request: Request, view: ChangeFormView, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "changes/form.html", {"nav_active": "changes", "view": view},
        status_code=status_code,
    )  # fmt: skip


def _detail_page(request: Request, view: ChangeDetailView, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "changes/detail.html", {"nav_active": "changes", "view": view},
        status_code=status_code,
    )  # fmt: skip


@router.get("/changes", response_class=HTMLResponse)
def changes(
    request: Request,
    session: SessionDep,
    scope: AccessibleSitesDep,
    site_id: int | None = None,
    show: Literal["open", "all"] = "open",
) -> HTMLResponse:
    view = service.build_list(session, scope, site_id, show)
    if view is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return templates.TemplateResponse(
        request, "changes/list.html", {"nav_active": "changes", "view": view}
    )


@router.get("/changes/new", response_class=HTMLResponse)
def new_change(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    site_id: int,
    item_id: int,
    case_id: int | None = None,
) -> HTMLResponse:
    return _form_page(request, service.new_form_view(session, user, site_id, item_id, case_id))


@router.post("/changes")
def propose(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    site_id: Annotated[int, Form()],
    work_item_id: Annotated[str, Form()] = "",
    case_id: Annotated[str, Form()] = "",
    title: Annotated[str, Form()] = "",
    after_work_date: Annotated[str, Form()] = "",
    after_start: Annotated[str, Form()] = "",
    after_end: Annotated[str, Form()] = "",
    after_location: Annotated[str, Form()] = "",
    reasons: Annotated[list[str] | None, Form()] = None,
    basis_note: Annotated[str, Form()] = "",
    plan_version: Annotated[str, Form()] = "",
    submit: Annotated[str, Form()] = "draft",
) -> Response:
    form = ChangeForm(
        work_item_id=work_item_id,
        case_id=case_id,
        title=title,
        after_work_date=after_work_date,
        after_start=after_start,
        after_end=after_end,
        after_location=after_location,
        reasons=tuple(reasons or ()),
        basis_note=basis_note,
        plan_version=plan_version,
        submit=submit,
    )
    new_case, errors = service.propose(session, user, site_id, form, now.date(), now)
    if new_case is None:
        item_id = int(work_item_id) if work_item_id.isdigit() else 0
        existing = int(case_id) if case_id.isdigit() else None
        view = service.new_form_view(session, user, site_id, item_id, existing, form, errors)
        return _form_page(request, view, status_code=422)
    return RedirectResponse(f"/changes/{new_case}?done=proposed", status_code=303)


@router.get("/changes/{case_id}", response_class=HTMLResponse)
def detail(
    request: Request, session: SessionDep, user: CurrentUserDep, case_id: int, done: str = ""
) -> HTMLResponse:
    view = service.build_detail(session, user, case_id, message=MESSAGES.get(done))
    return _detail_page(request, view)


def _after_action(
    request: Request,
    session: Session,
    user: CurrentUserDep,
    case_id: int,
    errors: tuple[str, ...],
    done: str,
) -> Response:
    if errors:
        view = service.build_detail(session, user, case_id, errors=errors)
        return _detail_page(request, view, status_code=409)
    return RedirectResponse(f"/changes/{case_id}?done={done}", status_code=303)


@router.post("/changes/{case_id}/revisions/{revision_id}/submit")
def submit(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    case_id: int,
    revision_id: int,
    site_id: Annotated[int, Form()],
) -> Response:
    errors = service.submit(session, user, site_id, case_id, revision_id, now)
    return _after_action(request, session, user, case_id, errors, "submitted")


@router.post("/changes/{case_id}/revisions/{revision_id}/confirm")
def confirm(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    case_id: int,
    revision_id: int,
    site_id: Annotated[int, Form()],
    confirm_key: Annotated[str, Form()] = "",
) -> Response:
    outcome, errors = service.confirm(
        session, user, site_id, case_id, revision_id, confirm_key, now
    )
    done = "already" if outcome == "already" else "confirmed"
    return _after_action(request, session, user, case_id, errors, done)


@router.post("/changes/{case_id}/revisions/{revision_id}/withdraw")
def withdraw(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    case_id: int,
    revision_id: int,
    site_id: Annotated[int, Form()],
    reason: Annotated[str, Form()] = "",
) -> Response:
    errors = service.withdraw(session, user, site_id, case_id, revision_id, reason, now)
    return _after_action(request, session, user, case_id, errors, "withdrawn")
