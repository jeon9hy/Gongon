from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.core.params import OptionalSiteIdQuery
from app.core.templating import register_template_dir, templates
from app.features.auth.service import CurrentUserDep, require_user
from app.features.judgments import service as judgments_service
from app.features.schedules import service
from app.features.schedules.holidays import HolidayLookupDep
from app.features.schedules.importer import MAX_IMPORT_BYTES, ImportFileError, read_rows
from app.features.schedules.schemas import ScheduleView, WorkItemEditForm, WorkItemForm
from app.features.teams.schemas import CATEGORY_LABELS
from app.features.teams.service import AccessibleSitesDep, ManagedSitesDep, ProposableSitesDep

register_template_dir(Path(__file__).parent / "templates")

# 모든 화면은 로그인이 필요하다(D-057).
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]


def _render(
    request: Request,
    view: ScheduleView,
    manageable: frozenset[int],
    session: Session,
    now: datetime,
    status_code: int = 200,
    proposable: frozenset[int] = frozenset(),
) -> HTMLResponse:
    # 달력 칸·날 상세의 판정 단계(D-085). 판정 범위(내일부터 7일) 작업만 단계가 있다.
    shown = (
        [s.site_id for s in view.sites] if view.all_mode else [view.site_id] if view.site_id else []
    )
    marks = judgments_service.item_verdicts(session, shown, now)
    context = {"nav_active": "schedule", "view": view, "manageable": manageable,
               "proposable": proposable or manageable, "categories": CATEGORY_LABELS,
               "marks": marks}  # fmt: skip
    return templates.TemplateResponse(
        request, "schedules/index.html", context, status_code=status_code
    )


@router.get("/schedule", response_class=HTMLResponse)
def schedule(
    request: Request,
    session: SessionDep,
    scope: AccessibleSitesDep,
    manageable: ManagedSitesDep,
    proposable: ProposableSitesDep,
    now: NowDep,
    holidays_of: HolidayLookupDep,
    site_id: OptionalSiteIdQuery = None,
    month: str | None = None,
    day: str | None = None,
    saved: bool = False,
    deleted: bool = False,
    edited: bool = False,
    unchanged: bool = False,
    imported: int | None = None,
    skipped: int = 0,
) -> HTMLResponse:
    message = (
        f"공정표에서 작업 {imported}건을 등록했습니다."
        + (f" 이미 있는 {skipped}건은 건너뛰었습니다." if skipped else "")
        if imported is not None
        else "작업을 추가했습니다."
        if saved
        else "작업을 지웠습니다."
        if deleted
        else "작업 계획을 바꿨습니다. 바뀐 시간·위치로 다시 판정하세요."
        if edited
        else "바뀐 내용이 없어 저장하지 않았습니다."
        if unchanged
        else None
    )
    view = service.build_view(
        session,
        scope,
        site_id,
        now.date(),
        message=message,
        month=month,
        day=day,
        now_hm=f"{now:%H:%M}",
        holidays_of=holidays_of,
    )
    if view is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    return _render(request, view, manageable, session, now, proposable=proposable)


@router.post("/schedule")
def add_item(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    manageable: ManagedSitesDep,
    now: NowDep,
    holidays_of: HolidayLookupDep,
    site_id: Annotated[int, Form()],
    work_types: Annotated[list[str] | None, Form()] = None,
    work_date: Annotated[str, Form()] = "",
    start: Annotated[str, Form()] = "",
    end: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    memo: Annotated[str, Form()] = "",
    work_dates: Annotated[list[str] | None, Form()] = None,
    performing_participant_id: Annotated[str, Form()] = "",
    date_mode: Annotated[str, Form()] = "pick",
    range_start: Annotated[str, Form()] = "",
    range_end: Annotated[str, Form()] = "",
    weekdays: Annotated[list[str] | None, Form()] = None,
) -> Response:
    form = WorkItemForm(
        work_types=tuple(work_types or ()),
        work_date=work_date,
        start=start,
        end=end,
        location=location,
        memo=memo,
        work_dates=tuple(work_dates or ()),
        performing_participant_id=performing_participant_id,
        date_mode=date_mode,
        range_start=range_start,
        range_end=range_end,
        weekdays=tuple(weekdays or ()),
    )
    first_day, errors = service.add_item(session, user, site_id, form, now)
    if first_day is None:
        view = service.build_view(
            session, scope, site_id, now.date(), form, errors, now_hm=f"{now:%H:%M}",
            holidays_of=holidays_of,
        )  # fmt: skip
        if view is None:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
        return _render(request, view, manageable, session, now, status_code=422)
    return RedirectResponse(
        f"/schedule?site_id={site_id}&day={first_day.isoformat()}&saved=1", status_code=303
    )


CONFLICT_MESSAGE = "다른 사람이 먼저 이 작업을 바꿨습니다. 최신 내용을 확인한 뒤 다시 저장하세요."


@router.post("/schedule/{item_id}/edit")
def edit_item(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    manageable: ManagedSitesDep,
    now: NowDep,
    holidays_of: HolidayLookupDep,
    item_id: int,
    site_id: Annotated[int, Form()],
    day: Annotated[str, Form()] = "",
    work_date: Annotated[str, Form()] = "",
    start: Annotated[str, Form()] = "",
    end: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    memo: Annotated[str, Form()] = "",
    performing_participant_id: Annotated[str, Form()] = "",
    plan_version: Annotated[str, Form()] = "",
) -> Response:
    form = WorkItemEditForm(
        work_date, start, end, location, memo, performing_participant_id, plan_version
    )
    result, errors = service.update_item(session, user, site_id, item_id, form, now)
    if result == "missing":
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    if result == "conflict" or errors:
        view = service.build_view(
            session, scope, site_id, now.date(), day=day, edit_item_id=item_id,
            now_hm=f"{now:%H:%M}", holidays_of=holidays_of,
            edit_errors=(CONFLICT_MESSAGE,) if result == "conflict" else errors,
        )  # fmt: skip
        if view is None:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
        status = 409 if result == "conflict" else 422
        return _render(request, view, manageable, session, now, status_code=status)
    flag = "edited" if result == "saved" else "unchanged"
    return RedirectResponse(
        f"/schedule?site_id={site_id}&day={work_date or day}&{flag}=1", status_code=303
    )


@router.post("/schedule/{item_id}/delete")
def delete_item(
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    item_id: int,
    site_id: Annotated[int, Form()],
    day: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if not service.delete_item(session, user, site_id, item_id, now):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    return RedirectResponse(f"/schedule?site_id={site_id}&day={day}&deleted=1", status_code=303)


@router.post("/schedule/import")
async def import_schedule(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    scope: AccessibleSitesDep,
    manageable: ManagedSitesDep,
    now: NowDep,
    holidays_of: HolidayLookupDep,
    site_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
) -> Response:
    """공정표 파일(엑셀·CSV)로 작업을 한꺼번에 등록한다(C04-30, D-086). 조정자만."""
    data = await file.read(MAX_IMPORT_BYTES + 1)
    try:
        rows = read_rows(file.filename or "", data)
        result = service.import_items(session, user, site_id, rows, now)
        errors = result.errors
    except ImportFileError as error:
        result, errors = None, (str(error),)
    if errors or result is None:
        view = service.build_view(session, scope, site_id, now.date(), now_hm=f"{now:%H:%M}",
                                  holidays_of=holidays_of)  # fmt: skip
        if view is None:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
        view = replace(view, import_errors=errors)
        return _render(request, view, manageable, session, now, status_code=422)
    day = f"&day={result.first_day.isoformat()}" if result.first_day else ""
    return RedirectResponse(
        f"/schedule?site_id={site_id}{day}&imported={result.added}&skipped={result.skipped}",
        status_code=303,
    )
