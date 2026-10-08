"""작업 일정(S08-1). 판정 기능은 items_on·items_on_for_sites·items_between으로 작업을 읽는다."""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.features.schedules import repository
from app.features.schedules.models import WorkItem
from app.features.schedules.schemas import (
    CalendarDay,
    DayDetail,
    ScheduleView,
    SiteChoice,
    WorkItemForm,
    WorkItemRecord,
)
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteRecord

CELL_ITEMS = 3  # 달력 칸에 보이는 작업 수(나머지는 +N)
MAX_LOCATION = 60
MAX_MEMO = 500
_WEEKDAYS = "월화수목금토일"


def items_on(session: Session, site_id: int, day: date) -> tuple[WorkItemRecord, ...]:
    return tuple(_record(i) for i in repository.list_between(session, [site_id], day, day))


def items_between(
    session: Session, site_id: int, start: date, end: date
) -> dict[date, tuple[WorkItemRecord, ...]]:
    """한 현장의 [start, end] 작업을 날짜별로(쿼리 1회). 작업 없는 날은 빠진다."""
    by_day: dict[date, list[WorkItemRecord]] = {}
    for item in repository.list_between(session, [site_id], start, end):
        by_day.setdefault(item.work_date, []).append(_record(item))
    return {day: tuple(items) for day, items in by_day.items()}


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
    month: str | None = None,
    day: str | None = None,
) -> ScheduleView | None:
    """월 달력 + 고른 날짜 상세. 현장이 없으면 빈 화면, 없는 site_id면 None.

    month(YYYY-MM)·day(YYYY-MM-DD)가 형식에 맞지 않으면 무시하고 기본값(내일이 든 달·내일)을 쓴다.
    """
    sites = sites_service.list_sites(session)
    site = _pick(sites, site_id)
    if sites and site is None:
        return None
    tomorrow = today + timedelta(days=1)
    selected = _date(day or "") or (_date(form.work_date) if form else None) or tomorrow
    first = _month(month or "") or selected.replace(day=1)
    if (selected.year, selected.month) != (first.year, first.month):
        # 달만 바꿔 왔으면 그 달에 내일이 있으면 내일, 없으면 1일을 고른다.
        in_month = (tomorrow.year, tomorrow.month) == (first.year, first.month)
        selected = tomorrow if in_month else first
    grid_start = first - timedelta(days=first.weekday())
    last = _month_end(first)
    grid_end = last + timedelta(days=6 - last.weekday())

    weeks: tuple[tuple[CalendarDay, ...], ...] = ()
    detail = None
    if site is not None:
        items = [
            _record(i)
            for i in repository.list_between(session, [site.site_id], grid_start, grid_end)
        ]
        by_day: dict[date, list[WorkItemRecord]] = {}
        for item in items:
            by_day.setdefault(item.work_date, []).append(item)

        def href(d: date) -> str:
            return f"/schedule?site_id={site.site_id}&month={d:%Y-%m}&day={d.isoformat()}"

        cells = []
        d = grid_start
        while d <= grid_end:
            on_day = by_day.get(d, [])
            cells.append(
                CalendarDay(
                    day=d,
                    href=href(d),
                    in_month=d.month == first.month,
                    is_today=d == today,
                    is_target=d == tomorrow,
                    in_period=site.works_on(d),
                    selected=d == selected,
                    items=tuple(on_day[:CELL_ITEMS]),
                    more=max(0, len(on_day) - CELL_ITEMS),
                )
            )
            d += timedelta(days=1)
        weeks = tuple(tuple(cells[i : i + 7]) for i in range(0, len(cells), 7))
        detail = _detail(site, selected, today, tuple(by_day.get(selected, [])))

    default_form = WorkItemForm(
        work_type="" if site is None or not site.work_types else site.work_types[0],
        work_date=selected.isoformat(),
        start="" if site is None else f"{site.work_start_local:%H:%M}",
        end="" if site is None else f"{site.work_end_local:%H:%M}",
    )
    base = "" if site is None else f"/schedule?site_id={site.site_id}&month="
    return ScheduleView(
        sites=tuple(
            SiteChoice(s.site_id, s.name, site is not None and s.site_id == site.site_id)
            for s in sites
        ),
        site_id=None if site is None else site.site_id,
        site_name="" if site is None else site.name,
        period_text=None if site is None else site.period_text(),
        month_title=f"{first.year}년 {first.month}월",
        prev_href=f"{base}{(first - timedelta(days=1)):%Y-%m}",
        next_href=f"{base}{(last + timedelta(days=1)):%Y-%m}",
        this_month_href=f"{base}{tomorrow:%Y-%m}&day={tomorrow.isoformat()}",
        weeks=weeks,
        detail=detail,
        work_types=() if site is None else site.work_types,
        form=form or default_form,
        errors=errors,
        message=message,
    )


def _detail(
    site: SiteRecord, day: date, today: date, items: tuple[WorkItemRecord, ...]
) -> DayDetail:
    if day <= today:
        note: str | None = (
            "지난 날짜와 오늘은 작업을 추가할 수 없습니다(판정은 다음 날 작업을 봅니다)."
        )
    elif not site.works_on(day):
        note = f"현장 작업 기간({site.period_text()}) 밖입니다."
    elif not items:
        note = "등록한 작업 없음 · 현장 기본 작업 시간으로 판정합니다."
    else:
        note = None
    return DayDetail(
        day=day,
        day_text=_day_text(day),
        is_target=day == today + timedelta(days=1),
        can_add=day > today and site.works_on(day),
        note=note,
        items=items,
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


def _month(raw: str) -> date | None:
    try:
        year, month = raw.strip().split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        return None


def _month_end(first: date) -> date:
    next_first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_first - timedelta(days=1)


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
