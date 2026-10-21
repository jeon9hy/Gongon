"""작업 일정(S08-1). 판정 기능은 items_on·items_on_for_sites·items_between으로 작업을 읽는다."""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.rules import basis_status, judges_weather
from app.core.work_kinds import WORK_KIND_NAMES, WORK_TRADES, trade_key
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser
from app.features.schedules import repository
from app.features.schedules.importer import ImportRow
from app.features.schedules.models import WorkItem, WorkItemRevision
from app.features.schedules.schemas import (
    CalendarDay,
    DayDetail,
    DetailGroup,
    MonthChoice,
    ParticipantChoice,
    PickerField,
    PickerTrade,
    PlanChangeResult,
    PlanValues,
    RevisionView,
    ScheduleView,
    SiteChoice,
    WorkItemEditForm,
    WorkItemForm,
    WorkItemRecord,
    WorkTypeChoice,
)
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteRecord, SiteScope
from app.features.teams import service as teams_service
from app.features.teams.schemas import MANAGE_ROLES, ParticipantOption
from engine.kst import KST

# 업체별·위치별 묶음(D-085). 묶음 이름이 없을 때 쓰는 이름.
UNASSIGNED = "업체 미정"
NO_PLACE = "위치 없음"
_BUILDING = re.compile(r"(\d+)\s*동")
_FLOOR = re.compile(r"(지하\s*|[Bb])?(\d+)(\s*~\s*\d+)?\s*층")
MONTH_PICK_SPAN = 6  # 달 고르기 목록에 늘 넣는 보고 있는 달 앞뒤 개월 수
MONTH_PICK_MAX = 24  # 달 고르기 목록은 보고 있는 달에서 앞뒤 최대 이 개월까지
# 전체 달력은 이 해들 사이를 고를 수 있다(개발자 요청 2026-10-17)
ALL_MODE_FIRST_YEAR = 2020
ALL_MODE_LAST_YEAR = 2100
MAX_LOCATION = 60
MAX_DAYS = 31  # 한 번에 추가할 수 있는 날 수
MAX_ITEMS = 100  # 한 번에 만들 수 있는 작업 수(공종 수 x 날 수)
MAX_RANGE_DAYS = 92  # 기간 고르기의 최대 길이(시작일~종료일)
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


def items_between_for_sites(
    session: Session, site_ids: list[int], start: date, end: date
) -> list[WorkItemRecord]:
    """여러 현장의 [start, end] 작업(쿼리 한 번, 날짜·시작 순). 홈의 공온 점검이 쓴다."""
    return [_record(i) for i in repository.list_between(session, site_ids, start, end)]


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
    now_hm: str = "",
    holidays_of: Callable[[int], Mapping[date, str]] = lambda year: {},
) -> ScheduleView | None:
    """월 달력 + 고른 날짜 상세. 현장이 없으면 빈 화면, 없거나 범위 밖 site_id면 None.

    month(YYYY-MM)·day(YYYY-MM-DD)가 형식에 맞지 않으면 무시하고 기본값(오늘이 든 달·오늘)을 쓴다.
    """
    sites = sites_service.list_sites(session, scope)
    site = _pick(sites, site_id)
    if site_id is not None and site is None:
        return None  # 없거나 참여하지 않은 현장(D-057)
    # 현장을 고르지 않고 들어오면(메뉴·주소) 현장이 둘 이상일 때 전체를 보인다(2026-10-17 요청)
    all_mode = site_id is None and len(sites) > 1
    if all_mode:
        site = None
    shown: list[SiteRecord] = list(sites) if all_mode else ([site] if site is not None else [])
    tomorrow = today + timedelta(days=1)
    selected = _date(day or "") or (_date(form.work_date) if form else None) or today
    first = _month(month or "") or selected.replace(day=1)
    if all_mode:
        first = min(max(first, date(ALL_MODE_FIRST_YEAR, 1, 1)), date(ALL_MODE_LAST_YEAR, 12, 1))
    if site is not None and not _overlaps_period([site], first):
        # 작업 기간 밖의 달은 열지 않는다(개발자 요청): 가까운 기간 끝 달로 옮긴다
        start, end = site.work_start_date, site.work_end_date
        edge = start if start is not None and first < start else end
        if edge is not None:
            first = edge.replace(day=1)
    if (selected.year, selected.month) != (first.year, first.month):
        # 달만 바꿔 왔으면 그 달에 오늘이 있으면 오늘, 없으면 1일을 고른다.
        in_month = (today.year, today.month) == (first.year, first.month)
        selected = today if in_month else first
    # 달력은 일요일부터(개발자, D-065). weekday()는 월=0이라 일요일까지 하루 더 당긴다.
    grid_start = first - timedelta(days=(first.weekday() + 1) % 7)
    last = _month_end(first)
    grid_end = last + timedelta(days=(5 - last.weekday()) % 7)

    weeks: tuple[tuple[CalendarDay, ...], ...] = ()
    detail = None
    labels: dict[int, str] = {}
    choices: tuple[ParticipantOption, ...] = ()
    revisions: dict[int, tuple[RevisionView, ...]] = {}
    site_names = {s.site_id: s.name for s in shown}
    if shown:
        items = [
            _record(i)
            for i in repository.list_between(
                session, [s.site_id for s in shown], grid_start, grid_end
            )
        ]
        by_day: dict[date, list[WorkItemRecord]] = {}
        for item in items:
            by_day.setdefault(item.work_date, []).append(item)

        def href(d: date) -> str:
            prefix = "/schedule?" if site is None else f"/schedule?site_id={site.site_id}&"
            return f"{prefix}month={d:%Y-%m}&day={d.isoformat()}"

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
                    in_period=_works_on(shown, d),
                    selected=d == selected,
                    addable=d >= today and _works_on(shown, d),
                    holiday=holidays_of(d.year).get(d),
                    item_ids=tuple(i.item_id for i in on_day),
                    warn=any(i.performing_participant_id is None for i in on_day)
                    or bool(overlapping_ids(on_day)),
                )
            )
            d += timedelta(days=1)
        weeks = tuple(tuple(cells[i : i + 7]) for i in range(0, len(cells), 7))
        for s in shown:  # 전체에서는 현장 수만큼(현장은 몇 곳뿐이다)
            labels |= teams_service.participant_labels(session, s.site_id)
        names = {pid: label.split(" · ")[0] for pid, label in labels.items()}
        trades = teams_service.company_trades(session, [s.site_id for s in shown])
        detail = _detail(shown, selected, today, tuple(by_day.get(selected, [])), names, trades)
        if site is not None:
            choices = teams_service.participant_choices(session, site.site_id)
        revisions = _revision_views(session, [i.item_id for i in detail.items], labels)

    # 공종·시간은 미리 고르지 않는다(개발자 요청). 날짜만 고른 날로 채운다.
    default_form = WorkItemForm(
        work_date=selected.isoformat(),
        range_start=selected.isoformat(),
        range_end=selected.isoformat(),
    )
    shown_form = form or default_form
    kinds = () if site is None else _work_type_choices(session, site.site_id, shown_form)
    base = "/schedule?month=" if site is None else f"/schedule?site_id={site.site_id}&month="
    return ScheduleView(
        sites=tuple(
            SiteChoice(s.site_id, s.name, site is not None and s.site_id == site.site_id)
            for s in sites
        ),
        site_id=None if site is None else site.site_id,
        site_name="전체" if all_mode else ("" if site is None else site.name),
        all_mode=all_mode,
        site_names=site_names,
        period_text=None if site is None else site.period_text(),
        month_title=f"{first.year}년 {first.month}월",
        prev_href=_nav_href(shown, base, (first - timedelta(days=1)).replace(day=1), all_mode),
        next_href=_nav_href(shown, base, last + timedelta(days=1), all_mode),
        this_month_href=f"{base}{today:%Y-%m}&day={today.isoformat()}",
        month_groups=() if not shown else _month_groups(shown, first, tomorrow, base, all_mode),
        pick_years=(ALL_MODE_FIRST_YEAR, ALL_MODE_LAST_YEAR) if all_mode else None,
        weeks=weeks,
        detail=detail,
        work_types=kinds,
        work_picker=_work_picker(kinds),
        form=shown_form,
        errors=errors,
        message=message,
        has_partners=site is not None and has_partner_companies(session, site.site_id),
        participants=tuple(
            ParticipantChoice(
                c.participant_id,
                c.name,
                str(c.participant_id) == shown_form.performing_participant_id,
                c.group_label,
                " ".join(k for name in c.work_trades if (k := trade_key(name))),
            )
            for c in choices
        ),
        participant_names=labels,
        revisions=revisions,
        edit_item_id=edit_item_id,
        edit_errors=edit_errors,
        today_iso=today.isoformat(),
        now_hm=now_hm,
        period_start_iso=""
        if site is None or site.work_start_date is None
        else site.work_start_date.isoformat(),
        period_end_iso=""
        if site is None or site.work_end_date is None
        else site.work_end_date.isoformat(),
    )


def _detail(
    shown: list[SiteRecord],
    day: date,
    today: date,
    items: tuple[WorkItemRecord, ...],
    names: Mapping[int, str],
    trades: Mapping[int, str],
) -> DayDetail:
    if day < today:
        note: str | None = "지난 날짜는 작업을 추가할 수 없습니다."
    elif not _works_on(shown, day):
        note = (
            f"현장 작업 기간({shown[0].period_text()}) 밖입니다."
            if len(shown) == 1
            else "어느 현장도 작업하지 않는 날입니다."
        )
    elif day == today:
        # 판정은 내일부터 7일(D-041)이라 오늘 작업은 일정·변경 관리로만 쓴다(C04-4).
        note = "오늘 작업은 일정·변경 관리용입니다. 기상 판정은 내일 작업부터 합니다."
    elif not items:
        note = "등록한 작업 없음 · 작업이 없는 날은 판정하지 않습니다."
    else:
        note = None
    return DayDetail(
        day=day,
        day_text=_day_text(day),
        is_target=day == today + timedelta(days=1),
        can_add=day >= today and _works_on(shown, day),
        note=note,
        items=items,
        by_company=_detail_groups(items, "company", names, trades),
        by_place=_detail_groups(items, "place", names, trades),
    )


def _detail_groups(
    items: tuple[WorkItemRecord, ...],
    by: str,
    names: Mapping[int, str],
    trades: Mapping[int, str],
) -> tuple[DetailGroup, ...]:
    """날 상세 묶음(D-085). 업체별은 업종 메모, 위치별은 참여 업체를 작은 글자로."""
    warned = overlapping_ids(items) | {
        i.item_id for i in items if i.performing_participant_id is None
    }
    groups: list[DetailGroup] = []
    for label, group in group_items(items, by, names):
        first = group[0].performing_participant_id
        if by == "company":
            sub = "" if first is None else trades.get(first, "")
        else:
            who = list(dict.fromkeys(
                names.get(i.performing_participant_id, UNASSIGNED)
                if i.performing_participant_id is not None else UNASSIGNED
                for i in group
            ))  # fmt: skip
            sub = who[0] + (f" 외 {len(who) - 1}" if len(who) > 1 else "")
        groups.append(DetailGroup(label, sub, tuple(group), by == "company" and first is None
                                  and label == UNASSIGNED,
                                  frozenset(i.item_id for i in group) & warned))  # fmt: skip
    return tuple(groups)


def add_item(
    session: Session, user: CurrentUser, site_id: int, form: WorkItemForm, now: datetime
) -> tuple[date | None, tuple[str, ...]]:
    """검증에 통과하면 고른 공종 x 날짜마다 작업을 저장한다. (첫 작업 날짜, 오류 목록).

    하나라도 맞지 않으면 아무것도 저장하지 않는다. 비참여 현장은 404, 조정자가 아니면 403(teams)."""
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        return None, ("현장을 찾을 수 없습니다.",)
    if not has_partner_companies(session, site_id):
        return None, (NO_COMPANY,)
    performer, performer_error = _performer(session, site_id, form.performing_participant_id)
    items, errors = _validate(site, form, now)
    if performer_error:
        errors = (*errors, performer_error)
    if not items or performer_error:
        return None, errors
    for item in items:
        item.performing_participant_id = performer
    repository.add_all(session, items)
    return min(i.work_date for i in items), ()


def update_item(
    session: Session,
    user: CurrentUser,
    site_id: int,
    item_id: int,
    form: WorkItemEditForm,
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
    performer, performer_error = _performer(
        session, site_id, form.performing_participant_id, keep=item.performing_participant_id
    )
    as_add = WorkItemForm((item.work_type,), form.work_date, form.start, form.end,
                          form.location, form.memo)  # fmt: skip
    # 이미 시작한 오늘 작업의 끝 시각·위치만 고칠 때는 '지금 이후 시작' 규칙을 다시 묻지 않는다.
    validated, errors = _validate(site, as_add, now, keep=(item.work_date, item.start_local))
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


def get_item(session: Session, site_id: int, item_id: int) -> WorkItemRecord | None:
    """지우지 않은 작업 하나(다른 현장의 작업은 None). 변경 건이 현재 계획을 읽을 때 쓴다."""
    item = repository.get_active(session, site_id, item_id)
    return None if item is None else _record(item)


def items_by_ids(session: Session, item_ids: list[int]) -> dict[int, WorkItemRecord]:
    """여러 작업을 쿼리 한 번으로(지운 작업은 빠진다)."""
    return {i.id: _record(i) for i in repository.get_many(session, item_ids)}


def apply_plan_change_by_id(
    session: Session,
    site_id: int,
    item_id: int,
    expected_version: int,
    values: PlanValues,
    *,
    changed_by: int | None,
    now: datetime,
    source: str,
) -> PlanChangeResult:
    """다른 기능(변경 확정)이 부르는 계획 저장. 커밋하지 않는다. 지운·다른 현장 작업이면 missing."""
    item = repository.get_active(session, site_id, item_id)
    if item is None:
        return "missing"
    return apply_plan_change(
        session, item, expected_version, values, changed_by=changed_by, now=now, source=source
    )


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


NO_COMPANY = "먼저 참여 업체를 등록해 주세요. 원청 말고 일할 업체가 있어야 작업을 올릴 수 있어요."


def has_partner_companies(session: Session, site_id: int) -> bool:
    """원청 말고 참여 중인 업체가 하나라도 있는가(작업 추가 조건, D-076)."""
    return any(c.group_label != "원청" for c in teams_service.participant_choices(session, site_id))


def _performer(
    session: Session, site_id: int, raw: str, keep: int | None = None
) -> tuple[int | None, str | None]:
    """실행 업체 입력 → 참여 업체 ID. 작업마다 실행 업체가 있어야 한다(D-076).

    참여 중인 이 현장 업체만 고를 수 있다(D-066). 수정할 때 이미 연결된 업체(keep)는 참여
    종료했어도 그대로 둘 수 있다(기존 연결 유지)."""
    if not raw.strip():
        return None, "실행 업체를 골라 주세요."
    participant_id = _int(raw)
    if participant_id is not None and participant_id == keep:
        return participant_id, None
    active = {c.participant_id for c in teams_service.participant_choices(session, site_id)}
    if participant_id is None or participant_id not in active:
        return None, "실행 업체는 이 현장의 참여 업체 중 참여 중인 곳에서 고르세요."
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


def plan_start_error(
    work_date: date, start: time, now: datetime, keep: tuple[date, time] | None = None
) -> str | None:
    """D-064: 추가·계획 수정·변경 제안/확정에 같은 시작 시각 규칙을 쓴다."""
    local_now = now.astimezone(KST)
    today = local_now.date()
    if work_date < today:
        return "지난 날짜에는 작업 계획을 바꿀 수 없습니다. 오늘 이후 날짜를 고르세요."
    if (
        work_date == today
        and start <= local_now.time().replace(second=0, microsecond=0)
        and keep != (today, start)
    ):
        return f"오늘 작업은 지금({local_now:%H:%M}) 이후 시작 시각으로 등록하세요."
    return None


def _validate(
    site: SiteRecord,
    form: WorkItemForm,
    now: datetime,
    keep: tuple[date, time] | None = None,
) -> tuple[list[WorkItem], tuple[str, ...]]:
    """고른 공종 x 날짜마다 작업 하나씩(여러 공종·여러 날 한 번에 추가).

    하나라도 맞지 않으면 아무것도 만들지 않는다.
    """
    errors: list[str] = []
    local_now = now.astimezone(KST)
    today = local_now.date()
    work_types = tuple(dict.fromkeys(w for w in form.work_types if w))
    if not work_types:
        errors.append("작업을 하나 이상 고르세요.")
    elif any(w not in WORK_KIND_NAMES for w in work_types):
        errors.append("목록에 있는 작업을 고르세요.")
    days, date_error = _form_days(form)
    if date_error:
        errors.append(date_error)
    elif len(days) > MAX_DAYS:
        errors.append(f"한 번에 {MAX_DAYS}일까지 추가할 수 있습니다.")
    elif any(d < today for d in days):
        errors.append("지난 날짜에는 작업을 추가할 수 없습니다. 오늘 이후 날짜를 고르세요.")
    elif not all(site.works_on(d) for d in days):
        errors.append(f"현장 작업 기간({site.period_text()}) 안의 날짜를 고르세요.")
    elif len(work_types) * len(days) > MAX_ITEMS:
        errors.append(
            f"한 번에 작업 {MAX_ITEMS}건까지 추가할 수 있습니다"
            f"(작업 {len(work_types)}개 × {len(days)}일 = {len(work_types) * len(days)}건)."
        )
    start, end = _time(form.start), _time(form.end)
    if start is None or end is None:
        errors.append("작업 시간을 00:00 형식으로 입력하세요.")
    elif start >= end:
        errors.append("작업 종료는 시작보다 늦어야 합니다(같은 날 안에서).")
    elif today in days and (start_error := plan_start_error(today, start, now, keep)):
        errors.append(start_error)
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
                work_type=w,
                work_date=d,
                start_local=start,
                end_local=end,
                location=location,
                memo=memo,
            )
            for d in days
            for w in work_types
        ],
        (),
    )


def _form_days(form: WorkItemForm) -> tuple[list[date], str | None]:
    """화면에서 고른 날짜들. 기간 고르기면 시작일~종료일 중 고른 요일만."""
    if form.date_mode == "range":
        start, end = _date(form.range_start), _date(form.range_end)
        if start is None or end is None:
            return [], "기간의 시작일·종료일을 날짜 형식으로 입력하세요."
        if end < start:
            return [], "기간의 종료일은 시작일과 같거나 늦어야 합니다."
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            return [], f"기간은 {MAX_RANGE_DAYS}일까지 고를 수 있습니다."
        weekdays = {int(w) for w in form.weekdays if w in {"0", "1", "2", "3", "4", "5", "6"}}
        if not weekdays:
            return [], "요일을 하나 이상 고르세요."
        span = [start + timedelta(days=n) for n in range((end - start).days + 1)]
        days = [d for d in span if d.weekday() in weekdays]
        if not days:
            return [], "고른 기간에 해당 요일이 없습니다."
        return days, None
    raw_days = [r for r in (*form.work_dates, form.work_date) if r.strip()]
    parsed = [_date(r) for r in raw_days]
    if not raw_days:
        return [], "작업 날짜를 고르세요."
    if None in parsed:
        return [], "작업 날짜를 날짜 형식으로 입력하세요."
    return sorted({d for d in parsed if d is not None}), None


def _work_type_choices(
    session: Session, site_id: int, form: WorkItemForm
) -> tuple[WorkTypeChoice, ...]:
    """고를 수 있는 작업 전체. 이 현장에서 많이 쓴 작업을 앞에, 나머지는 목록 순서."""
    usage = repository.work_type_usage(session, site_id)
    order = sorted(WORK_KIND_NAMES, key=lambda w: (-usage.get(w, 0), WORK_KIND_NAMES.index(w)))
    return tuple(
        WorkTypeChoice(w, basis_status(w), w in form.work_types, usage.get(w, 0), judges_weather(w))
        for w in order
    )


def _work_picker(choices: tuple[WorkTypeChoice, ...]) -> tuple[PickerTrade, ...]:
    """업종 → 업무분야 → 작업(D-085). 이 현장에서 쓴 작업이 있으면 맨 앞에 '자주 쓴 작업'."""
    if not choices:
        return ()
    by_name = {c.label: c for c in choices}
    trades = [
        PickerTrade(f"t{n}", trade.name, trade.legal, tuple(
            PickerField(f"t{n}-f{m}", field.name, tuple(by_name[k] for k in field.kinds))
            for m, field in enumerate(trade.fields)
        ))
        for n, trade in enumerate(WORK_TRADES)
    ]  # fmt: skip
    used = tuple(c for c in choices if c.used)  # choices는 많이 쓴 순
    if used:
        recent = PickerField("recent-f0", "이 현장에서 쓴 순", used)
        trades.insert(0, PickerTrade("recent", "자주 쓴 작업", False, (recent,)))
    return tuple(trades)


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


def _works_on(sites: list[SiteRecord], day: date) -> bool:
    return any(s.works_on(day) for s in sites)


def _month_groups(
    sites: list[SiteRecord], shown: date, tomorrow: date, base: str, all_mode: bool = False
) -> tuple[tuple[int, tuple[MonthChoice, ...]], ...]:
    """달 고르기 목록: 보고 있는 달 앞뒤 MONTH_PICK_SPAN개월 + 작업 기간 + 내일이 든 달.

    작업 기간이 너무 길면 보고 있는 달 중심 앞뒤 MONTH_PICK_MAX개월로 자른다.
    """
    anchors = [shown, tomorrow.replace(day=1)]
    for site in sites:
        for edge in (site.work_start_date, site.work_end_date):
            if edge is not None:
                anchors.append(edge.replace(day=1))
    # 작업 기간이 짧아도 앞뒤로 넘겨 볼 수 있게 보고 있는 달 앞뒤 MONTH_PICK_SPAN개월은 항상 넣는다.
    anchors += [_add_months(shown, -MONTH_PICK_SPAN), _add_months(shown, MONTH_PICK_SPAN)]
    start, end = min(anchors), max(anchors)
    start = max(start, _add_months(shown, -MONTH_PICK_MAX))
    end = min(end, _add_months(shown, MONTH_PICK_MAX))
    if all_mode:  # 전체 달력: 보고 있는 해 앞뒤 한 해(나머지 해는 화면 스크립트가 만든다)
        start = date(max(ALL_MODE_FIRST_YEAR, shown.year - 1), 1, 1)
        end = date(min(ALL_MODE_LAST_YEAR, shown.year + 1), 12, 1)
    # 한 해를 3줄 4칸으로 보이므로 해의 1월~12월을 모두 채운다(기간 밖 달은 막힘으로 보인다)
    start, end = start.replace(month=1), end.replace(month=12)

    groups: dict[int, list[MonthChoice]] = {}
    month = start
    while month <= end:
        groups.setdefault(month.year, []).append(
            MonthChoice(
                label=f"{month.month}월",
                href=f"{base}{month:%Y-%m}",
                selected=month == shown,
                in_period=all_mode or _overlaps_period(sites, month),
                is_target=month == tomorrow.replace(day=1),
            )
        )
        month = _add_months(month, 1)
    return tuple((year, tuple(months)) for year, months in groups.items())


def _nav_href(
    sites: list[SiteRecord], base: str, first: date, all_mode: bool = False
) -> str | None:
    """이전·다음 달 주소. 보이는 현장 모두의 작업 기간 밖이면 None(버튼을 막는다).

    전체 달력은 2020년 1월~2100년 12월 밖만 막는다.
    """
    if all_mode:
        inside = date(ALL_MODE_FIRST_YEAR, 1, 1) <= first <= date(ALL_MODE_LAST_YEAR, 12, 1)
        return f"{base}{first:%Y-%m}" if inside else None
    if sites and not _overlaps_period(sites, first):
        return None
    return f"{base}{first:%Y-%m}"


def _overlaps_period(sites: list[SiteRecord], first: date) -> bool:
    """이 달 중 하루라도 어느 현장의 작업 기간에 드는가(기간 끝이 비면 그쪽 제한 없음)."""
    end_of_month = _month_end(first)
    return any(
        (s.work_start_date is None or s.work_start_date <= end_of_month)
        and (s.work_end_date is None or s.work_end_date >= first)
        for s in sites
    )


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


def place_key(location: str) -> str:
    """작업 위치 → 위치별 묶음 이름(동·층). '101동 9층 2구역' → '101동 9층'.

    동·층을 못 찾으면 적은 위치 그대로('자재 야적장'), 비어 있으면 NO_PLACE. 위치는 자유 입력이라
    추정하지 않고 글자에 있는 동·층만 쓴다.
    """
    text = location.strip()
    if not text:
        return NO_PLACE
    building = _BUILDING.search(text)
    floor = _FLOOR.search(text)
    parts = [f"{building.group(1)}동"] if building else []
    if floor:
        parts.append(re.sub(r"\s+", "", floor.group(0)))
    return " ".join(parts) or text


def place_order(key: str) -> tuple[float, float, str]:
    """위치 묶음 순서: 동 번호 → 층(지하는 음수) → 이름. 위치 없음은 맨 뒤."""
    if key == NO_PLACE:
        return (float("inf"), float("inf"), key)
    building = _BUILDING.search(key)
    floor = _FLOOR.search(key)
    floor_no = float("inf")
    if floor:
        floor_no = -float(floor.group(2)) if floor.group(1) else float(floor.group(2))
    return (float(building.group(1)) if building else float("inf"), floor_no, key)


def group_items(
    items: Iterable[WorkItemRecord], by: str, companies: Mapping[int, str]
) -> list[tuple[str, list[WorkItemRecord]]]:
    """작업을 업체별(by='company') 또는 위치별(by='place')로 묶는다. 묶음 안은 시작 시각 순.

    업체별은 업체 미정을 맨 앞(점검 문제), 나머지는 이름 순. 위치별은 동·층 순.
    """
    groups: dict[str, list[WorkItemRecord]] = {}
    for item in sorted(items, key=lambda i: (i.start_local, i.item_id)):
        if by == "place":
            key = place_key(item.location)
        else:
            pid = item.performing_participant_id
            key = companies.get(pid, UNASSIGNED) if pid is not None else UNASSIGNED
        groups.setdefault(key, []).append(item)
    if by == "place":
        return sorted(groups.items(), key=lambda g: place_order(g[0]))
    return sorted(groups.items(), key=lambda g: (g[0] != UNASSIGNED, g[0]))


def overlapping_ids(items: Iterable[WorkItemRecord]) -> set[int]:
    """같은 현장·날짜·위치에서 시간이 겹치는 작업(공온 점검의 겹침과 같은 기준, D-065)."""
    found: set[int] = set()
    listed = [i for i in items if i.location]
    for n, a in enumerate(listed):
        for b in listed[n + 1 :]:
            if (a.site_id, a.work_date, a.location) == (b.site_id, b.work_date, b.location) and (
                a.start_local < b.end_local and b.start_local < a.end_local
            ):
                found |= {a.item_id, b.item_id}
    return found


@dataclass(frozen=True, slots=True)
class ImportResult:
    """공정표 가져오기 결과(C04-30). errors가 있으면 아무것도 저장하지 않았다."""

    added: int
    skipped: int  # 이미 같은 작업이 있거나 파일 안에서 같은 줄이 반복돼 건너뜀
    first_day: date | None
    errors: tuple[str, ...]


def import_items(
    session: Session,
    user: CurrentUser,
    site_id: int,
    rows: list[ImportRow],
    now: datetime,
) -> ImportResult:
    """공정표 행을 작업으로 등록한다(D-086). 행마다 작업 추가와 같은 검사를 한다.

    한 줄이라도 틀리면 아무것도 저장하지 않는다(줄 번호와 이유를 돌려준다). 같은 작업(날짜·시간·
    작업·위치·실행 업체)이 이미 있거나 파일 안에서 반복되면 건너뛴다. 그래서 같은 파일을 두 번
    올려도 작업이 두 벌 생기지 않는다. 실행 업체는 이 현장 참여 업체의 이름과 똑같아야 한다.
    """
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        return ImportResult(0, 0, None, ("현장을 찾을 수 없습니다.",))
    if not rows:
        return ImportResult(0, 0, None, ("등록할 줄이 없습니다.",))
    companies: dict[str, list[int]] = {}
    for option in teams_service.participant_choices(session, site_id):
        companies.setdefault(option.name.strip(), []).append(option.participant_id)
    errors: list[str] = []
    planned: list[WorkItem] = []
    for row in rows:
        form = WorkItemForm(
            work_types=(row.work_type,), work_dates=(row.work_date,), start=row.start,
            end=row.end, location=row.location, memo=row.memo,
        )  # fmt: skip
        items, row_errors = _validate(site, form, now)
        found = companies.get(row.company.strip(), [])
        problems = list(row_errors)
        if not row.company.strip():
            problems.append("실행업체를 적어 주세요.")
        elif not found:
            problems.append(f"'{row.company}'은(는) 이 현장 참여 업체가 아닙니다(이름을 똑같이).")
        elif len(found) > 1:
            problems.append(f"'{row.company}' 이름의 참여 업체가 여럿입니다.")
        if problems:
            errors.extend(f"{row.line}행: {p}" for p in problems)
            continue
        for item in items:
            item.performing_participant_id = found[0]
        planned.extend(items)
    if errors:
        return ImportResult(0, 0, None, tuple(errors))

    def key(i: WorkItem) -> tuple[object, ...]:
        return (i.work_type, i.work_date, i.start_local, i.end_local, i.location,
                i.performing_participant_id)  # fmt: skip

    days = [i.work_date for i in planned]
    seen = {key(i) for i in repository.list_between(session, [site_id], min(days), max(days))}
    new: list[WorkItem] = []
    for item in planned:
        if key(item) in seen:
            continue
        seen.add(key(item))
        new.append(item)
    repository.add_all(session, new)
    first = min((i.work_date for i in new), default=None)
    return ImportResult(len(new), len(planned) - len(new), first, ())
