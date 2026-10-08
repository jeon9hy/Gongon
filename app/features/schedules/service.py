"""작업 일정(S08-1). 판정 기능은 items_on·items_on_for_sites로 그날 작업을 읽는다."""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.features.schedules import repository
from app.features.schedules.models import WorkItem
from app.features.schedules.schemas import (
    DayGroup,
    ScheduleView,
    SiteChoice,
    WorkItemForm,
    WorkItemRecord,
)
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteRecord

VIEW_DAYS = 7  # 화면은 내일부터 일주일(단기예보로 판정할 수 있는 범위와 비슷하게)
MAX_LOCATION = 60
MAX_MEMO = 500
_WEEKDAYS = "월화수목금토일"


def items_on(session: Session, site_id: int, day: date) -> tuple[WorkItemRecord, ...]:
    return tuple(_record(i) for i in repository.list_between(session, [site_id], day, day))


def items_on_for_sites(
    session: Session, site_ids: list[int], day: date
) -> dict[int, tuple[WorkItemRecord, ...]]:
    """여러 현장의 그날 작업을 쿼리 한 번으로."""
    by_site: dict[int, list[WorkItemRecord]] = {}
    for item in repository.list_between(session, site_ids, day, day):
        by_site.setdefault(item.site_id, []).append(_record(item))
    return {site_id: tuple(items) for site_id, items in by_site.items()}


def build_view(
    session: Session,
    site_id: int | None,
    today: date,
    form: WorkItemForm | None = None,
    errors: tuple[str, ...] = (),
    message: str | None = None,
) -> ScheduleView | None:
    """현장이 없으면 빈 화면, 없는 site_id면 None."""
    sites = sites_service.list_sites(session)
    site = _pick(sites, site_id)
    if sites and site is None:
        return None
    tomorrow = today + timedelta(days=1)
    days: tuple[DayGroup, ...] = ()
    if site is not None:
        last = tomorrow + timedelta(days=VIEW_DAYS - 1)
        items = [
            _record(i) for i in repository.list_between(session, [site.site_id], tomorrow, last)
        ]
        days = tuple(
            DayGroup(
                day_text=_day_text(day),
                is_target=day == tomorrow,
                items=tuple(i for i in items if i.work_date == day),
            )
            for day in (tomorrow + timedelta(days=n) for n in range(VIEW_DAYS))
            if site.works_on(day)
        )
    default_form = WorkItemForm(
        work_type="" if site is None or not site.work_types else site.work_types[0],
        work_date=tomorrow.isoformat(),
        start="" if site is None else f"{site.work_start_local:%H:%M}",
        end="" if site is None else f"{site.work_end_local:%H:%M}",
    )
    return ScheduleView(
        sites=tuple(
            SiteChoice(s.site_id, s.name, site is not None and s.site_id == site.site_id)
            for s in sites
        ),
        site_id=None if site is None else site.site_id,
        site_name="" if site is None else site.name,
        period_text=None if site is None else site.period_text(),
        days=days,
        work_types=() if site is None else site.work_types,
        form=form or default_form,
        errors=errors,
        message=message,
    )


def add_item(
    session: Session, site_id: int, form: WorkItemForm, today: date
) -> tuple[bool, tuple[str, ...]]:
    """검증에 통과하면 저장한다. (저장 여부, 오류 목록). 없는 현장이면 (False, ("현장 없음",))."""
    site = sites_service.get_site(session, site_id)
    if site is None:
        return False, ("현장을 찾을 수 없습니다.",)
    item, errors = _validate(site, form, today)
    if item is None:
        return False, errors
    repository.add(session, item)
    return True, ()


def delete_item(session: Session, site_id: int, item_id: int) -> bool:
    return repository.delete_item(session, site_id, item_id)


def _validate(
    site: SiteRecord, form: WorkItemForm, today: date
) -> tuple[WorkItem | None, tuple[str, ...]]:
    errors: list[str] = []
    if form.work_type not in site.work_types:
        errors.append("현장에 등록한 공종 중에서 고르세요. 공종은 현장 설정에서 바꿉니다.")
    day = _date(form.work_date)
    if day is None:
        errors.append("작업 날짜를 입력하세요.")
    elif day <= today:
        errors.append("작업 날짜는 내일 이후여야 합니다(판정은 다음 날 작업을 봅니다).")
    elif not site.works_on(day):
        errors.append(f"현장 작업 기간({site.period_text()}) 안의 날짜를 고르세요.")
    start, end = _time(form.start), _time(form.end)
    if start is None or end is None:
        errors.append("작업 시간을 00:00 형식으로 입력하세요.")
    elif start >= end:
        errors.append("작업 종료는 시작보다 늦어야 합니다(같은 날 안에서).")
    location, memo = form.location.strip(), form.memo.strip()
    if len(location) > MAX_LOCATION:
        errors.append(f"작업 위치는 {MAX_LOCATION}자 이하로 입력하세요.")
    if len(memo) > MAX_MEMO:
        errors.append(f"메모는 {MAX_MEMO}자 이하로 입력하세요.")
    if errors or day is None or start is None or end is None:
        return None, tuple(errors)
    return (
        WorkItem(
            site_id=site.site_id,
            work_type=form.work_type,
            work_date=day,
            start_local=start,
            end_local=end,
            location=location,
            memo=memo,
        ),
        (),
    )


def _pick(sites: tuple[SiteRecord, ...], site_id: int | None) -> SiteRecord | None:
    if site_id is None:
        return sites[0] if sites else None
    return next((s for s in sites if s.site_id == site_id), None)


def _record(item: WorkItem) -> WorkItemRecord:
    return WorkItemRecord(
        item_id=item.id,
        site_id=item.site_id,
        work_type=item.work_type,
        work_date=item.work_date,
        start_local=item.start_local,
        end_local=item.end_local,
        location=item.location,
        memo=item.memo,
    )


def _day_text(day: date) -> str:
    return f"{day.month}월 {day.day}일({_WEEKDAYS[day.weekday()]})"


def _time(raw: str) -> time | None:
    try:
        return time.fromisoformat(raw.strip())
    except ValueError:
        return None


def _date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None
