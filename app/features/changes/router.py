from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.actions.schemas import ActionForm, CandidateForm
from app.features.auth.service import CurrentUserDep, require_user
from app.features.changes import service
from app.features.changes.schemas import ChangeDetailView, ChangeForm, ChangeFormView
from app.features.teams.service import AccessibleSitesDep
from engine.kst import KST

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]

MESSAGES = {
    "proposed": "변경을 제안했습니다.",
    "submitted": "영향 검토로 보냈습니다. 조정자가 확인한 뒤 확정합니다.",
    "confirmed": "변경을 확정했습니다. 작업 계획이 바뀌었고 후속 조치를 요청했습니다.",
    "already": "이미 확정된 요청입니다. 다시 저장하지 않았습니다.",
    "withdrawn": "제안을 철회했습니다.",
    "candidate": "조치 후보를 더했습니다.",
    "removed": "조치 후보를 뺐습니다.",
    "acted": "조치를 처리했습니다.",
    "closed": "변경 건을 종료했습니다.",
}


def _form_page(
    request: Request,
    view: ChangeFormView,
    now: datetime,
    status_code: int = 200,
    embed: bool = False,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "changes/form.html",
        {"nav_active": "changes", "view": view, "now": now.astimezone(KST), "embed": embed},
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
    now: NowDep,
    site_id: int,
    item_id: int,
    case_id: int | None = None,
    embed: bool = False,
) -> HTMLResponse:
    return _form_page(
        request, service.new_form_view(session, user, site_id, item_id, case_id), now, embed=embed
    )


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
    embed: Annotated[str, Form()] = "",
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
        return _form_page(request, view, now, status_code=422, embed=embed == "1")
    if embed == "1":
        return HTMLResponse(
            '<!doctype html><meta charset="utf-8"><script>'
            f'window.top.location.href = "/changes/{new_case}?done=proposed";</script>'
        )
    return RedirectResponse(f"/changes/{new_case}?done=proposed", status_code=303)


@router.get("/changes/{case_id}", response_class=HTMLResponse)
def detail(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    case_id: int,
    done: str = "",
) -> HTMLResponse:
    view = service.build_detail(session, user, case_id, now, message=MESSAGES.get(done))
    return _detail_page(request, view)


def _after_action(
    request: Request,
    session: Session,
    user: CurrentUserDep,
    case_id: int,
    now: datetime,
    errors: tuple[str, ...],
    done: str,
    anchor: str = "",
) -> Response:
    if errors:
        view = service.build_detail(session, user, case_id, now, errors=errors)
        return _detail_page(request, view, status_code=409)
    return RedirectResponse(f"/changes/{case_id}?done={done}{anchor}", status_code=303)


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
    return _after_action(request, session, user, case_id, now, errors, "submitted")


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
    no_action_reason: Annotated[str, Form()] = "",
) -> Response:
    outcome, errors = service.confirm(
        session, user, site_id, case_id, revision_id, confirm_key, now, no_action_reason
    )
    done = "already" if outcome == "already" else "confirmed"
    return _after_action(request, session, user, case_id, now, errors, done)


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
    return _after_action(request, session, user, case_id, now, errors, "withdrawn")


# ---------- 후속 조치(C06) ----------


@router.post("/changes/{case_id}/revisions/{revision_id}/actions")
def add_candidate(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    case_id: int,
    revision_id: int,
    site_id: Annotated[int, Form()],
    title: Annotated[str, Form()] = "",
    done_criteria: Annotated[str, Form()] = "",
    performing_participant_id: Annotated[str, Form()] = "",
    assignee: Annotated[str, Form()] = "",
    verifier_user_id: Annotated[str, Form()] = "",
    required: Annotated[str, Form()] = "",
    due_date: Annotated[str, Form()] = "",
    due_time: Annotated[str, Form()] = "",
    due_note: Annotated[str, Form()] = "",
) -> Response:
    form = CandidateForm(
        title=title,
        done_criteria=done_criteria,
        performing_participant_id=performing_participant_id,
        assignee=assignee,
        verifier_user_id=verifier_user_id,
        required=required == "1",
        due_date=due_date,
        due_time=due_time,
        due_note=due_note,
    )
    errors = service.add_action_candidate(session, user, site_id, case_id, revision_id, form, now)
    if errors:
        view = service.build_detail(
            session, user, case_id, now, errors=errors,
            candidate_form=form, candidate_errors=errors, candidate_revision_id=revision_id,
        )  # fmt: skip
        return _detail_page(request, view, status_code=422)
    return RedirectResponse(f"/changes/{case_id}?done=candidate#rev-{revision_id}", status_code=303)


@router.post("/changes/{case_id}/revisions/{revision_id}/actions/{action_id}/remove")
def remove_candidate(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    case_id: int,
    revision_id: int,
    action_id: int,
    site_id: Annotated[int, Form()],
) -> Response:
    errors = service.remove_action_candidate(
        session, user, site_id, case_id, revision_id, action_id
    )
    return _after_action(request, session, user, case_id, now, errors, "removed",
                         f"#rev-{revision_id}")  # fmt: skip


@router.post("/changes/{case_id}/actions/{action_id}/{kind}")
def act(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    case_id: int,
    action_id: int,
    kind: str,
    site_id: Annotated[int, Form()],
    revision_id: Annotated[str, Form()] = "",
    body: Annotated[str, Form()] = "",
    performed_date: Annotated[str, Form()] = "",
    performed_time: Annotated[str, Form()] = "",
    counterpart: Annotated[str, Form()] = "",
    reference: Annotated[str, Form()] = "",
    contacted_date: Annotated[str, Form()] = "",
    contacted_time: Annotated[str, Form()] = "",
    resolver: Annotated[str, Form()] = "",
) -> Response:
    form = ActionForm(
        revision_id=revision_id,
        body=body,
        performed_date=performed_date,
        performed_time=performed_time,
        counterpart=counterpart,
        reference=reference,
        contacted_date=contacted_date,
        contacted_time=contacted_time,
        resolver=resolver,
    )
    errors = service.act_on_action(session, user, site_id, case_id, action_id, kind, form, now)
    return _after_action(request, session, user, case_id, now, errors, "acted",
                         f"#action-{action_id}")  # fmt: skip


@router.post("/changes/{case_id}/close")
def close(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    case_id: int,
    site_id: Annotated[int, Form()],
) -> Response:
    errors = service.close_case(session, user, site_id, case_id, now)
    return _after_action(request, session, user, case_id, now, errors, "closed")
