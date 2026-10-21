from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth.schemas import CurrentUser
from app.features.auth.service import CurrentUserDep, require_user
from app.features.sites import service as sites_service
from app.features.teams import service
from app.features.teams.schemas import ContactForm, MemberForm, MembersView, ParticipantForm
from app.features.teams.service import AccessibleSitesDep

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


def _site_name(session: Session, site_id: int, scope: frozenset[int]) -> str:
    site = sites_service.get_site(session, site_id, scope)
    if site is None:
        raise HTTPException(status_code=404, detail=service.NOT_FOUND)
    return site.name


def _render(request: Request, view: MembersView, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "teams/members.html",
        {"nav_active": "sites", "view": view},
        status_code=status_code,
    )


@router.get("/sites/{site_id}/members", response_class=HTMLResponse)
def members(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    site_id: int,
    done: str = "",
) -> HTMLResponse:
    name = _site_name(session, site_id, scope)
    view = service.build_members_view(session, site_id, name, user, message=MESSAGES.get(done))
    return _render(request, view)


@router.post("/sites/{site_id}/members")
def add_member(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    now: NowDep,
    site_id: int,
    email: Annotated[str, Form()] = "",
    role: Annotated[str, Form()] = "",
    contact_id: Annotated[str, Form()] = "",
    same_name: Annotated[str, Form()] = "",
) -> Response:
    name = _site_name(session, site_id, scope)
    errors = service.add_member(session, site_id, user, email, role, now, contact_id, same_name)
    if errors:
        form = MemberForm(email.strip(), role, contact_id, same_name)
        return _failed(request, session, user, site_id, name, errors, member_form=form)
    return _done(site_id, "added")


@router.post("/sites/{site_id}/members/{membership_id}/revoke")
def revoke_member(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    now: NowDep,
    site_id: int,
    membership_id: int,
) -> Response:
    name = _site_name(session, site_id, scope)
    errors = service.revoke_member(session, site_id, user, membership_id, now)
    if errors:
        return _failed(request, session, user, site_id, name, errors)
    if service.role_on(session, user.user_id, site_id) is None:
        # 자기 권한을 회수했으면 이 현장은 더 볼 수 없다
        return RedirectResponse("/sites", status_code=303)
    return _done(site_id, "revoked")


MESSAGES = {
    "added": "참여자를 추가했습니다.",
    "revoked": "권한을 회수했습니다.",
    "registered": "업체를 등록했어요.",
    "edited": "업체 정보를 고쳤어요.",
    "ended": "참여를 종료했어요. 지난 작업 연결은 그대로예요.",
    "resumed": "참여를 다시 시작했어요.",
    "contact": "담당자를 명부에 넣었어요.",
    "removed": "명부에서 뺐어요.",
    "linked": "계정을 연결했어요.",
    "unlinked": "계정 연결을 풀었어요.",
}


def _done(site_id: int, key: str) -> RedirectResponse:
    return RedirectResponse(f"/sites/{site_id}/members?done={key}", status_code=303)


def _failed(
    request: Request,
    session: Session,
    user: CurrentUser,
    site_id: int,
    name: str,
    errors: tuple[str, ...],
    **view_args: Any,
) -> HTMLResponse:
    view = service.build_members_view(session, site_id, name, user, errors=errors, **view_args)
    return _render(request, view, status_code=422)


@router.post("/sites/{site_id}/participants")
def register_participant(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    site_id: int,
    organization_name: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "",
    trade_note: Annotated[str, Form()] = "",
    business_no: Annotated[str, Form()] = "",
    joined_on: Annotated[str, Form()] = "",
    confirm_same_name: Annotated[str, Form()] = "",
    return_to: Annotated[str, Form()] = "",
    work_trades: Annotated[list[str] | None, Form()] = None,
) -> Response:
    name = _site_name(session, site_id, scope)
    form = ParticipantForm(organization_name, category, trade_note, business_no, joined_on,
                           confirm_same_name == "1", tuple(work_trades or ()))  # fmt: skip
    errors, same_names = service.register_participant(session, site_id, user, form)
    if errors:
        return _failed(request, session, user, site_id, name, errors,
                       participant_form=form, participant_same_name=same_names)  # fmt: skip
    if return_to.startswith(f"/schedule?site_id={site_id}&") and "//" not in return_to:
        # 작업 추가 중 업체를 등록했으면 그 화면으로 돌아가 작업 추가 창을 다시 연다
        return RedirectResponse(f"{return_to}&add=1", status_code=303)
    return _done(site_id, "registered")


@router.post("/sites/{site_id}/participants/{participant_id}/edit")
def edit_participant(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    site_id: int,
    participant_id: int,
    category: Annotated[str, Form()] = "",
    trade_note: Annotated[str, Form()] = "",
    business_no: Annotated[str, Form()] = "",
    joined_on: Annotated[str, Form()] = "",
    work_trades: Annotated[list[str] | None, Form()] = None,
) -> Response:
    name = _site_name(session, site_id, scope)
    form = ParticipantForm("", category, trade_note, business_no, joined_on,
                           work_trades=tuple(work_trades or ()))  # fmt: skip
    errors = service.edit_participant(session, site_id, user, participant_id, form)
    if errors:
        return _failed(request, session, user, site_id, name, errors)
    return _done(site_id, "edited")


@router.post("/sites/{site_id}/participants/{participant_id}/end")
def end_participant(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    now: NowDep,
    site_id: int,
    participant_id: int,
) -> Response:
    name = _site_name(session, site_id, scope)
    errors = service.end_participant(session, site_id, user, participant_id, now)
    if errors:
        return _failed(request, session, user, site_id, name, errors)
    return _done(site_id, "ended")


@router.post("/sites/{site_id}/participants/{participant_id}/resume")
def resume_participant(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    site_id: int,
    participant_id: int,
) -> Response:
    name = _site_name(session, site_id, scope)
    errors = service.resume_participant(session, site_id, user, participant_id)
    if errors:
        return _failed(request, session, user, site_id, name, errors)
    return _done(site_id, "resumed")


@router.post("/sites/{site_id}/participants/{participant_id}/contacts")
def add_contact(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    now: NowDep,
    site_id: int,
    participant_id: int,
    contact_name: Annotated[str, Form()] = "",
    job_title: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    memo: Annotated[str, Form()] = "",
) -> Response:
    name = _site_name(session, site_id, scope)
    form = ContactForm(contact_name, job_title, phone, memo)
    errors = service.add_contact(session, site_id, user, participant_id, form, now)
    if errors:
        return _failed(request, session, user, site_id, name, errors)
    return _done(site_id, "contact")


@router.post("/sites/{site_id}/contacts/{contact_id}/remove")
def remove_contact(
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    now: NowDep,
    site_id: int,
    contact_id: int,
) -> Response:
    _site_name(session, site_id, scope)
    service.remove_contact(session, site_id, user, contact_id, now)
    return _done(site_id, "removed")


@router.post("/sites/{site_id}/contacts/{contact_id}/link")
def link_contact(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    site_id: int,
    contact_id: int,
    email: Annotated[str, Form()] = "",
) -> Response:
    name = _site_name(session, site_id, scope)
    errors = service.link_contact(session, site_id, user, contact_id, email)
    if errors:
        return _failed(request, session, user, site_id, name, errors)
    return _done(site_id, "linked")


@router.post("/sites/{site_id}/contacts/{contact_id}/unlink")
def unlink_contact(
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    site_id: int,
    contact_id: int,
) -> Response:
    _site_name(session, site_id, scope)
    service.unlink_contact(session, site_id, user, contact_id)
    return _done(site_id, "unlinked")
