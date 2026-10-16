"""작업 일정(S08-1). 판정 기능은 items_on·items_on_for_sites·items_between으로 작업을 읽는다."""

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser
from app.features.schedules import repository
from app.features.schedules.models import WorkItem, WorkItemRevision
from app.features.schedules.schemas import (
    CalendarDay,
    DayDetail,
    MonthChoice,
    ParticipantChoice,
    PlanChangeResult,
    PlanValues,
    RevisionView,
    ScheduleView,
    SiteChoice,
    WorkItemEditForm,
    WorkItemForm,
    WorkItemRecord,
)
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteRecord, SiteScope
from app.features.teams import service as teams_service
from app.features.teams.schemas import MANAGE_ROLES
from engine.kst import KST

CELL_ITEMS = 3  # 달력 칸에 보이는 작업 수(나머지는 +N)
MONTH_PICK_SPAN = 6  # 달 고르기 목록에 늘 넣는 보고 있는 달 앞뒤 개월 수
MONTH_PICK_MAX = 24  # 달 고르기 목록은 보고 있는 달에서 앞뒤 최대 이 개월까지
MAX_LOCATION = 60
MAX_DAYS = 31  # 한 번에 추가할 수 있는 날 수
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
    scope: SiteScope,
    site_id: int | None,
    today: date,
    form: WorkItemForm | None = None,
    errors: tuple[str, ...] = (),
    message: str | None = None,
    month: str | None = None,
    day: str | None = None,
    edit_item_id: int | None = None,
    edit_errors: tuple[str, ...] = (),
) -> ScheduleView | None:
    """월 달력 + 고른 날짜 상세. 현장이 없으면 빈 화면, 없거나 범위 밖 site_id면 None.

    month(YYYY-MM)·day(YYYY-MM-DD)가 형식에 맞지 않으면 무시하고 기본값(내일이 든 달·내일)을 쓴다.
    """
    sites = sites_service.list_sites(session, scope)
    site = _pick(sites, site_id)
    if site_id is not None and site is None:
        return None  # 없거나 참여하지 않은 현장(D-057)
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
    labels: dict[int, str] = {}
    revisions: dict[int, tuple[RevisionView, ...]] = {}
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
                    addable=d > today and site.works_on(d),
                    items=tuple(on_day[:CELL_ITEMS]),
                    more=max(0, len(on_day) - CELL_ITEMS),
                )
            )
            d += timedelta(days=1)
        weeks = tuple(tuple(cells[i : i + 7]) for i in range(0, len(cells), 7))
        detail = _detail(site, selected, today, tuple(by_day.get(selected, [])))
        labels = teams_service.participant_labels(session, site.site_id)
        revisions = _revision_views(session, [i.item_id for i in detail.items], labels)

    # 공종·시간은 미리 고르지 않는다(개발자 요청). 날짜만 고른 날로 채운다.
    default_form = WorkItemForm(work_type="", work_date=selected.isoformat(), start="", end="")
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
        month_groups=() if site is None else _month_groups(site, first, tomorrow, base),
        weeks=weeks,
        detail=detail,
        work_types=() if site is None else site.work_types,
        form=form or default_form,
        errors=errors,
        message=message,
        participants=tuple(
            ParticipantChoice(
                pid, name, str(pid) == (form or default_form).performing_participant_id
            )
            for pid, name in labels.items()
        ),
        participant_names=labels,
        revisions=revisions,
        edit_item_id=edit_item_id,
        edit_errors=edit_errors,
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
    session: Session, user: CurrentUser, site_id: int, form: WorkItemForm, today: date
) -> tuple[bool, tuple[str, ...]]:
    """검증에 통과하면 저장한다. (저장 여부, 오류 목록). 없는 현장이면 (False, ("현장 없음",)).

    비참여 현장은 404, 조정자가 아니면 403(teams)."""
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        return False, ("현장을 찾을 수 없습니다.",)
    performer, performer_error = _performer(session, site_id, form.performing_participant_id)
    items, errors = _validate(site, form, today)
    if performer_error:
        errors = (*errors, performer_error)
    if not items or performer_error:
        return False, errors
    for item in items:
        item.performing_participant_id = performer
    repository.add_all(session, items)
    return True, ()


def update_item(
    session: Session,
    user: CurrentUser,
    site_id: int,
    item_id: int,
    form: WorkItemEditForm,
    today: date,
    now: datetime,
) -> tuple[PlanChangeResult, tuple[str, ...]]:
    """작업 일정 화면의 계획 수정. 조정자만. 화면을 연 뒤 다른 사람이 먼저 바꿨으면 conflict."""
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    site = sites_service.get_site(session, site_id, None)
    item = repository.get_active(session, site_id, item_id)
    if site is None or item is None:
        return "missing", ()
    expected = _int(form.plan_version)
    if expected is None:
        return "conflict", ()
    performer, performer_error = _performer(session, site_id, form.performing_participant_id)
    as_add = WorkItemForm(item.work_type, form.work_date, form.start, form.end, form.location,
                          form.memo)  # fmt: skip
    validated, errors = _validate(site, as_add, today)
    if performer_error:
        errors = (*errors, performer_error)
    if not validated or performer_error:
        return "unchanged", errors
    new = validated[0]
    values = PlanValues(new.work_date, new.start_local, new.end_local, new.location, new.memo,
                        performer)  # fmt: skip
    result = apply_plan_change(
        session, item, expected, values, changed_by=user.user_id, now=now, source="edit"
    )
    if result == "saved":
        session.commit()
    else:
        session.rollback()
    return result, ()


def apply_plan_change(
    session: Session,
    item: WorkItem,
    expected_version: int,
    values: PlanValues,
    *,
    changed_by: int | None,
    now: datetime,
    source: str,
) -> PlanChangeResult:
    """계획을 바꾸고 이전 값을 이력으로 남긴다. 커밋하지 않는다(C05 변경 확정과 한 트랜잭션).

    값이 그대로면 버전을 올리지 않는다. 제출 버전이 현재와 다르면(동시 수정) 아무것도 바꾸지 않는다.
    """
    if item.plan_version != expected_version:
        return "conflict"
    before = PlanValues(item.work_date, item.start_local, item.end_local, item.location,
                        item.memo, item.performing_participant_id)  # fmt: skip
    if before == values:
        return "unchanged"
    revision = WorkItemRevision(
        work_item_id=item.id,
        plan_version=expected_version,
        work_date=before.work_date,
        start_local=before.start_local,
        end_local=before.end_local,
        location=before.location,
        memo=before.memo,
        performing_participant_id=before.performing_participant_id,
        changed_by_user_id=changed_by,
        changed_at=now,
        source=source,
    )
    if not repository.update_plan_if_version(session, item, expected_version, values):
        return "conflict"  # 읽은 뒤 다른 요청이 먼저 저장했다
    session.add(revision)
    session.flush()
    return "saved"


def _performer(session: Session, site_id: int, raw: str) -> tuple[int | None, str | None]:
    """실행 업체 입력 → 참여 업체 ID. 빈 값은 미지정. 다른 현장의 참여 업체는 거부한다."""
    if not raw.strip():
        return None, None
    participant_id = _int(raw)
    if participant_id is None or participant_id not in teams_service.participant_labels(
        session, site_id
    ):
        return None, "실행 업체는 이 현장의 참여 업체 중에서 고르세요."
    return participant_id, None


def _int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def _revision_views(
    session: Session, item_ids: list[int], labels: dict[int, str]
) -> dict[int, tuple[RevisionView, ...]]:
    """고른 날 작업들의 변경 이력(쿼리: 이력 1회 + 사용자 1회)."""
    rows = repository.revisions_for(session, item_ids)
    users = auth_service.describe_users(
        session, (r.changed_by_user_id for r in rows if r.changed_by_user_id is not None)
    )
    by_item: dict[int, list[RevisionView]] = {}
    for r in rows:
        place = f" · {r.location}" if r.location else ""
        performer = (
            "실행 업체 미지정"
            if r.performing_participant_id is None
            else labels.get(r.performing_participant_id, "참여 종료 업체").split(" · ")[0]
        )
        who = users.get(r.changed_by_user_id or -1)
        by_item.setdefault(r.work_item_id, []).append(
            RevisionView(
                plan_version=r.plan_version,
                summary=f"{r.work_date:%m/%d} {r.start_local:%H:%M}–{r.end_local:%H:%M}"
                f"{place} · {performer}",
                changed_text=f"{r.changed_at.astimezone(KST):%m/%d %H:%M} "
                f"{who.display_name if who else '시스템'}",
            )
        )
    return {item_id: tuple(views) for item_id, views in by_item.items()}


def delete_item(
    session: Session, user: CurrentUser, site_id: int, item_id: int, now: datetime
) -> bool:
    """목록·판정에서 뺀다. 그 작업으로 낸 판정은 작업 연결과 함께 기록으로 남는다."""
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    return repository.delete_item(session, site_id, item_id, now)


def _validate(
    site: SiteRecord, form: WorkItemForm, today: date
) -> tuple[list[WorkItem], tuple[str, ...]]:
    """고른 날짜마다 작업 하나씩(여러 날 한 번에 추가).

    하루라도 맞지 않으면 아무것도 만들지 않는다.
    """
    errors: list[str] = []
    if not form.work_type:
        errors.append("공종을 고르세요.")
    elif form.work_type not in site.work_types:
        errors.append("현장에 등록한 공종 중에서 고르세요. 공종은 현장 설정에서 바꿉니다.")
    raw_days = [r for r in (*form.work_dates, form.work_date) if r.strip()]
    parsed = [_date(r) for r in raw_days]
    days = sorted({d for d in parsed if d is not None})
    if not raw_days:
        errors.append("작업 날짜를 고르세요.")
    elif None in parsed:
        errors.append("작업 날짜를 날짜 형식으로 입력하세요.")
    elif len(days) > MAX_DAYS:
        errors.append(f"한 번에 {MAX_DAYS}일까지 추가할 수 있습니다.")
    elif any(d <= today for d in days):
        errors.append("작업 날짜는 내일 이후여야 합니다(판정은 다음 날 작업을 봅니다).")
    elif not all(site.works_on(d) for d in days):
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
    if errors or start is None or end is None:
        return [], tuple(errors)
    return (
        [
            WorkItem(
                site_id=site.site_id,
                work_type=form.work_type,
                work_date=d,
                start_local=start,
                end_local=end,
                location=location,
                memo=memo,
            )
            for d in days
        ],
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
        performing_participant_id=item.performing_participant_id,
        plan_version=item.plan_version,
    )


def _month_groups(
    site: SiteRecord, shown: date, tomorrow: date, base: str
) -> tuple[tuple[int, tuple[MonthChoice, ...]], ...]:
    """달 고르기 목록: 보고 있는 달 앞뒤 MONTH_PICK_SPAN개월 + 작업 기간 + 내일이 든 달.

    작업 기간이 너무 길면 보고 있는 달 중심 앞뒤 MONTH_PICK_MAX개월로 자른다.
    """
    anchors = [shown, tomorrow.replace(day=1)]
    for edge in (site.work_start_date, site.work_end_date):
        if edge is not None:
            anchors.append(edge.replace(day=1))
    # 작업 기간이 짧아도 앞뒤로 넘겨 볼 수 있게 보고 있는 달 앞뒤 MONTH_PICK_SPAN개월은 항상 넣는다.
    anchors += [_add_months(shown, -MONTH_PICK_SPAN), _add_months(shown, MONTH_PICK_SPAN)]
    start, end = min(anchors), max(anchors)
    start = max(start, _add_months(shown, -MONTH_PICK_MAX))
    end = min(end, _add_months(shown, MONTH_PICK_MAX))

    groups: dict[int, list[MonthChoice]] = {}
    month = start
    while month <= end:
        groups.setdefault(month.year, []).append(
            MonthChoice(
                label=f"{month.month}월",
                href=f"{base}{month:%Y-%m}",
                selected=month == shown,
                in_period=_overlaps_period(site, month),
                is_target=month == tomorrow.replace(day=1),
            )
        )
        month = _add_months(month, 1)
    return tuple((year, tuple(months)) for year, months in groups.items())


def _overlaps_period(site: SiteRecord, first: date) -> bool:
    """이 달 중 하루라도 작업 기간에 드는가(기간 끝이 비어 있으면 그쪽으로 제한 없음)."""
    start, end = site.work_start_date, site.work_end_date
    return (start is None or start <= _month_end(first)) and (end is None or end >= first)


def _add_months(first: date, months: int) -> date:
    index = first.year * 12 + first.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


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
