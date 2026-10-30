"""변경과 이어진 서류(C14, D-112). 공온에 저장된 기록에서 규칙으로 만든다(LLM 없음).

- 주간 작업계획표(C14-1): 공정회의 자료. 월~일 업체별·요일별 작업, 공온 점검과 같은 기준의 점검,
  판정 범위 안 날의 판정 단계, 그 주 시작 전 7일 동안 확정된 변경, 지금 안 끝난 조치.
- 작업일보·공사일보(C14-2): 작업별 실제 결과(했음·일부만·못함 + 원인·인원·장비·메모).
  오늘까지의 작업만 기록하고, 조정자는 모든 작업, 담당자는 자기 업체가 실행하는 작업만
  기록한다. 계획과 달랐으면 변경 제안으로 잇는다(자동으로 변경을 만들지 않는다).
- 기상 작업중지 기록(C14-3): 작업일보에서 원인이 기상인 일부만·못함을 월별로, 작업 시작
  전 마지막 판정과 함께. 판정이 아니라 담당자가 남긴 실제 결과로 만든다. 공기 연장의
  공식 근거는 관측·계약 조건이다.
- 변경 건 문서(C14-4): 작업 지시서(업체별 조치·확인란)와 실정보고 초안(원인·근거·전후·
  버전·조치 결과). 변경 건 상세와 같은 값을 쓰며 발주처 양식으로 옮겨 쓰는 초안이다.
- 작업 차질 월 집계(C14-5): 작업일보의 일부만·못함을 원인별로, 적은 인원 합과 언제 알았나까지.
- 연락처·작업 메모는 넣지 않는다. 인쇄·PDF 저장용이며 공식 서류를 대신하지 않는다.
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.actions import service as actions_service
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser
from app.features.changes import service as changes_service
from app.features.changes.schemas import REASON_LABELS
from app.features.judgments import service as judgments_service
from app.features.reports.models import WorkReport
from app.features.reports.schemas import (
    CHANGE_DOC_TITLES,
    EQUIPMENT_MAX,
    KNOWN_LABELS,
    NOTE_MAX,
    OUTCOME_LABELS,
    WORKERS_MAX,
    ChangeDocKind,
    ChangeDocView,
    DailyRow,
    DailyView,
    DailyWork,
    LossRow,
    LossSummaryView,
    ReportForm,
    ReportInput,
    WeatherDay,
    WeatherEntry,
    WeatherLogView,
    WeeklyAction,
    WeeklyDay,
    WeeklyPlanView,
    WeeklyRow,
    WeeklyWork,
)
from app.features.schedules import service as schedules_service
from app.features.schedules.schemas import WorkItemRecord
from app.features.sites import service as sites_service
from app.features.teams import service as teams_service
from app.features.teams.schemas import ACTION_ROLES, ALL_ROLES
from engine.kst import KST

WEEK_DAYS = 7
UNASSIGNED = "실행 업체 미지정"
_WEEKDAYS = "월화수목금토일"


def week_start(now: datetime, requested: date | None) -> date:
    """보여 줄 주의 월요일. 고른 날이 있으면 그 주, 없으면 다음 주(공정회의는 다음 주를 맞춘다)."""
    if requested is not None:
        return requested - timedelta(days=requested.weekday())
    today = now.astimezone(KST).date()
    return today + timedelta(days=WEEK_DAYS - today.weekday())


def build_weekly(
    session: Session, user: CurrentUser, site_id: int, now: datetime, requested: date | None
) -> WeeklyPlanView:
    teams_service.require_role(session, user, site_id, ALL_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    start = week_start(now, requested)
    end = start + timedelta(days=WEEK_DAYS - 1)
    days = [start + timedelta(days=n) for n in range(WEEK_DAYS)]

    items = schedules_service.items_between_for_sites(session, [site_id], start, end)
    names = teams_service.company_names(session, [site_id])
    verdicts = judgments_service.item_verdicts(session, [site_id], now)
    open_changes = changes_service.open_change_item_ids(session, [i.item_id for i in items])
    overlaps = schedules_service.overlapping_ids(items)

    def issues(i: WorkItemRecord) -> tuple[str, ...]:
        found = []
        if not i.location:
            found.append("위치 없음")
        if i.item_id in overlaps:
            found.append("같은 곳 같은 시간")
        if i.item_id in open_changes:
            found.append("변경 검토 중")
        return tuple(found)

    def work(i: WorkItemRecord) -> WeeklyWork:
        verdict = verdicts.get(i.item_id)
        return WeeklyWork(
            time_text=f"{i.start_local:%H:%M}–{i.end_local:%H:%M}",
            work_type=i.work_type,
            location=i.location,
            verdict=verdict[0] if verdict else None,
            issues=issues(i),
        )

    def cells(group: list[WorkItemRecord]) -> tuple[tuple[WeeklyWork, ...], ...]:
        return tuple(
            tuple(work(i) for i in sorted(group, key=lambda i: i.start_local) if i.work_date == d)
            for d in days
        )

    grouped = _by_company(items)
    rows = [
        WeeklyRow(company=names.get(p, "이름 없음"), cells=cells(grouped[p]))
        for p in _company_order(session, site_id, grouped, names)
    ]
    if None in grouped:
        rows.append(WeeklyRow(company=UNASSIGNED, cells=cells(grouped[None]), unassigned=True))

    issue_count = sum(1 for i in items if i.performing_participant_id is None or issues(i))
    changes_from = datetime.combine(start - timedelta(days=WEEK_DAYS), time(0), KST)
    changes_to = datetime.combine(start, time(0), KST)
    actions = tuple(
        WeeklyAction(
            company=names.get(a.performing_participant_id, "이름 없음"),
            title=a.title,
            status_label=a.status_label,
            due_text=a.due_text,
            overdue=a.overdue,
            href=f"/changes/{a.case_id}#action-{a.action_id}",
        )
        for a in actions_service.open_at_site(session, site_id, now)
    )
    local = now.astimezone(KST)
    return WeeklyPlanView(
        site_id=site_id,
        site_name=site.name,
        period_text=f"{_long(start)} ~ {_long(end)}",
        days=tuple(
            WeeklyDay(iso=d.isoformat(), text=_short(d), holiday=d.weekday() >= 5) for d in days
        ),
        rows=tuple(rows),
        work_count=len(items),
        issue_count=issue_count,
        changes_period_text=f"{_short(start - timedelta(days=WEEK_DAYS))} ~ "
        f"{_short(start - timedelta(days=1))}",
        changes=changes_service.confirmed_between(session, site_id, changes_from, changes_to),
        actions=actions,
        prev_start=(start - timedelta(days=WEEK_DAYS)).isoformat(),
        next_start=(start + timedelta(days=WEEK_DAYS)).isoformat(),
        made_text=f"{_short(local.date())} {local:%H:%M} · {user.display_name}",
    )


def _by_company(items: list[WorkItemRecord]) -> dict[int | None, list[WorkItemRecord]]:
    grouped: dict[int | None, list[WorkItemRecord]] = {}
    for i in items:
        grouped.setdefault(i.performing_participant_id, []).append(i)
    return grouped


def _company_order(
    session: Session, site_id: int, grouped: dict[int | None, list[WorkItemRecord]],
    names: dict[int, str],
) -> list[int]:  # fmt: skip
    """작업이 있는 업체를 참여 업체 순(원청 → 구분 → 이름)으로.

    미지정(None)은 부르는 쪽이 맨 뒤에 붙인다.
    """
    order = [o.participant_id for o in teams_service.participant_choices(session, site_id)]
    # 참여를 끝낸 업체에 남은 작업도 빠뜨리지 않는다(이름 순으로 뒤에)
    ended = sorted((p for p in grouped if p is not None and p not in order),
                   key=lambda p: names.get(p, ""))  # fmt: skip
    return [p for p in (*order, *ended) if p in grouped]


def _short(day: date) -> str:
    return f"{day.month}/{day.day}({_WEEKDAYS[day.weekday()]})"


def _long(day: date) -> str:
    return f"{day.month}월 {day.day}일({_WEEKDAYS[day.weekday()]})"


def build_daily(
    session: Session,
    user: CurrentUser,
    site_id: int,
    now: datetime,
    requested: date | None,
    errors: tuple[str, ...] = (),
    error_item_id: int | None = None,
    error_form: ReportForm | None = None,
) -> DailyView:
    """공사일보: 그날 현장 작업을 업체별로, 작업마다 실제 결과와 고치기 폼.

    고치기 폼은 기록할 수 있는 사람에게만 보인다.
    """
    role = teams_service.require_role(session, user, site_id, ALL_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    today = now.astimezone(KST).date()
    day = requested or today
    items = schedules_service.items_between_for_sites(session, [site_id], day, day)
    names = teams_service.company_names(session, [site_id])
    reports = _reports_for(session, [i.item_id for i in items])
    recorders = auth_service.describe_users(
        session, (r.recorded_by_user_id for r in reports.values())
    )
    my_company = _my_company(session, user, site_id) if role == "assignee" else None
    recordable = day <= today

    def editable(i: WorkItemRecord) -> bool:
        if not recordable or role not in ACTION_ROLES:
            return False
        return role == "coordinator" or i.performing_participant_id == my_company

    def work(i: WorkItemRecord) -> DailyWork:
        r = reports.get(i.item_id)
        can_edit = editable(i)
        retry = error_form is not None and error_item_id == i.item_id
        form = error_form if retry and error_form is not None else _form_of(r)
        recorded = ""
        if r is not None:
            who = recorders.get(r.recorded_by_user_id)
            name = who.display_name if who else "알 수 없음"
            recorded = f"{r.recorded_at.astimezone(KST):%m/%d %H:%M} · {name}"
        return DailyWork(
            item_id=i.item_id,
            time_text=f"{i.start_local:%H:%M}–{i.end_local:%H:%M}",
            work_type=i.work_type,
            location=i.location,
            outcome=r.outcome if r else None,
            outcome_label=OUTCOME_LABELS[r.outcome] if r else "미입력",
            causes_text=" · ".join(REASON_LABELS.get(c, c) for c in r.causes) if r else "",
            known_text=_known_text(r),
            workers=r.workers if r else None,
            equipment_note=r.equipment_note if r else "",
            note=r.note if r else "",
            recorded_text=recorded,
            stale=r is not None and r.plan_version != i.plan_version,
            can_edit=can_edit,
            form=form,
            change_href=(
                f"/changes/new?site_id={site_id}&item_id={i.item_id}"
                if r is not None and r.outcome != "done" and can_edit
                else None
            ),
        )

    def row(company: str, group: list[WorkItemRecord], unassigned: bool = False) -> DailyRow:
        works = tuple(work(i) for i in sorted(group, key=lambda i: i.start_local))
        return DailyRow(
            company=company,
            works=works,
            workers_total=_sum(w.workers for w in works),
            unassigned=unassigned,
        )

    grouped = _by_company(items)
    rows = [
        row(names.get(p, "이름 없음"), grouped[p])
        for p in _company_order(session, site_id, grouped, names)
    ]
    if None in grouped:
        rows.append(row(UNASSIGNED, grouped[None], unassigned=True))
    start = datetime.combine(day, time(0), KST)
    local = now.astimezone(KST)
    return DailyView(
        site_id=site_id,
        site_name=site.name,
        day_iso=day.isoformat(),
        day_text=_long(day),
        recordable=recordable,
        rows=tuple(rows),
        work_count=len(items),
        recorded_count=len(reports),
        short_count=sum(1 for r in reports.values() if r.outcome != "done"),
        workers_total=_sum(r.workers for r in reports.values()),
        changes=changes_service.confirmed_between(
            session, site_id, start, start + timedelta(days=1)
        ),
        prev_day=(day - timedelta(days=1)).isoformat(),
        next_day=(day + timedelta(days=1)).isoformat(),
        made_text=f"{_short(local.date())} {local:%H:%M} · {user.display_name}",
        reason_labels=REASON_LABELS,
        outcome_labels=OUTCOME_LABELS,
        known_labels=KNOWN_LABELS,
        errors=errors,
        error_item_id=error_item_id,
    )


def save_report(
    session: Session,
    user: CurrentUser,
    site_id: int,
    item_id: int,
    form: ReportForm,
    now: datetime,
) -> tuple[date, tuple[str, ...]]:
    """작업 결과를 저장한다. (작업 날짜, 오류). 오류가 있으면 저장하지 않는다."""
    role = teams_service.require_role(session, user, site_id, ACTION_ROLES)
    item = schedules_service.get_item(session, site_id, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    if role == "assignee" and item.performing_participant_id != _my_company(session, user, site_id):
        raise HTTPException(status_code=403, detail="이 작업을 맡은 업체만 기록할 수 있습니다")
    if item.work_date > now.astimezone(KST).date():
        return item.work_date, ("작업일이 지나야 기록할 수 있어요. 오늘까지의 작업만 기록합니다.",)
    parsed, errors = validate_report(form)
    if parsed is None:
        return item.work_date, errors
    report = session.scalar(select(WorkReport).where(WorkReport.work_item_id == item_id))
    if report is None:
        report = WorkReport(site_id=site_id, work_item_id=item_id)
        session.add(report)
    report.work_date = item.work_date
    report.plan_version = item.plan_version
    report.outcome = parsed.outcome
    report.causes = list(parsed.causes)
    report.workers = parsed.workers
    report.equipment_note = parsed.equipment_note
    report.note = parsed.note
    report.known_when = parsed.known_when
    report.recorded_by_user_id = user.user_id
    report.recorded_at = now
    session.commit()
    return item.work_date, ()


def validate_report(form: ReportForm) -> tuple[ReportInput | None, tuple[str, ...]]:
    errors: list[str] = []
    if form.outcome not in OUTCOME_LABELS:
        errors.append("결과를 골라 주세요.")
    causes = tuple(dict.fromkeys(c for c in form.causes if c))
    if any(c not in REASON_LABELS for c in causes):
        errors.append("원인은 목록에서 골라 주세요.")
    if form.outcome in ("partial", "not_done") and not causes:
        errors.append("일부만 했거나 못 했으면 원인을 하나 이상 골라 주세요.")
    workers: int | None = None
    if form.workers.strip():
        try:
            workers = int(form.workers.strip())
        except ValueError:
            errors.append("인원은 숫자로 적어 주세요.")
        else:
            if not 0 <= workers <= WORKERS_MAX:
                errors.append(f"인원은 0~{WORKERS_MAX}명으로 적어 주세요.")
    equipment = form.equipment_note.strip()
    if len(equipment) > EQUIPMENT_MAX:
        errors.append(f"장비는 {EQUIPMENT_MAX}자까지 적을 수 있어요.")
    note = form.note.strip()
    if len(note) > NOTE_MAX:
        errors.append(f"메모는 {NOTE_MAX}자까지 적을 수 있어요.")
    known = form.known_when.strip()
    if known and known not in KNOWN_LABELS:
        errors.append("언제 알았는지는 목록에서 골라 주세요.")
    if errors:
        return None, tuple(errors)
    return ReportInput(
        outcome=form.outcome,
        causes=() if form.outcome == "done" else causes,  # 했음이면 원인을 남기지 않는다
        workers=workers,
        equipment_note=equipment,
        note=note,
        # 했음이면 비운다. 일부만·못함도 고르지 않았으면 모름(None)으로 둔다
        known_when=known or None if form.outcome != "done" else None,
    ), ()


def reports_between(session: Session, site_id: int, start: date, end: date) -> list[WorkReport]:
    """[start, end] 날짜의 작업 결과(쿼리 1회). 기상 작업중지 기록이 쓴다."""
    return list(
        session.scalars(
            select(WorkReport)
            .where(WorkReport.site_id == site_id, WorkReport.work_date.between(start, end))
            .order_by(WorkReport.work_date, WorkReport.id)
        )
    )


def _reports_for(session: Session, item_ids: list[int]) -> dict[int, WorkReport]:
    if not item_ids:
        return {}
    rows = session.scalars(select(WorkReport).where(WorkReport.work_item_id.in_(item_ids)))
    return {r.work_item_id: r for r in rows}


def _my_company(session: Session, user: CurrentUser, site_id: int) -> int | None:
    members = teams_service.memberships_of(session, user.user_id)
    return next((m.participant_id for m in members if m.site_id == site_id), None)


def _form_of(r: WorkReport | None) -> ReportForm:
    if r is None:
        return ReportForm()
    return ReportForm(
        outcome=r.outcome,
        causes=tuple(r.causes),
        workers="" if r.workers is None else str(r.workers),
        equipment_note=r.equipment_note,
        note=r.note,
        known_when=r.known_when or "",
    )


def _known_text(r: WorkReport | None) -> str:
    if r is None or r.known_when is None:
        return ""
    return f"{KNOWN_LABELS[r.known_when]} 알게 됨"


def _sum(values: Iterable[int | None]) -> int | None:
    """인원 합계. 적은 값이 하나도 없으면 None(0명으로 보이지 않게)."""
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def month_start(now: datetime, requested: str) -> date:
    """보여 줄 달의 1일. "2026-10" 같은 값이 아니면 이번 달."""
    try:
        year, month = (int(p) for p in requested.strip().split("-"))
        return date(year, month, 1)
    except ValueError:
        return now.astimezone(KST).date().replace(day=1)


def build_weather_log(
    session: Session, user: CurrentUser, site_id: int, now: datetime, requested: str
) -> WeatherLogView:
    teams_service.require_role(session, user, site_id, ALL_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    first = month_start(now, requested)
    last = _next_month(first) - timedelta(days=1)
    hit = [
        r
        for r in reports_between(session, site_id, first, last)
        if r.outcome != "done" and "weather" in r.causes
    ]
    items = schedules_service.items_by_ids(session, [r.work_item_id for r in hit])
    names = teams_service.company_names(session, [site_id])
    verdicts = judgments_service.verdicts_before_work(
        session, site_id, [(r.work_item_id, r.work_date) for r in hit]
    )
    per_day: dict[date, int] = {}
    for i in schedules_service.items_between_for_sites(session, [site_id], first, last):
        per_day[i.work_date] = per_day.get(i.work_date, 0) + 1

    def entry(r: WorkReport) -> WeatherEntry:
        i = items.get(r.work_item_id)
        verdict = verdicts.get((r.work_item_id, r.work_date))
        work, company = "지운 작업", "이름 없음"
        if i is not None:
            place = f" · {i.location}" if i.location else ""
            work = f"{i.work_type}{place} · {i.start_local:%H:%M}–{i.end_local:%H:%M}"
            company = names.get(i.performing_participant_id or -1, UNASSIGNED)
        verdict_text = "판정 기록 없음"
        if verdict is not None:
            at = verdict[1].astimezone(KST)
            verdict_text = f"{_short(at.date())} {at:%H:%M} 판정"
        return WeatherEntry(
            company=company,
            work_text=work,
            outcome_label=OUTCOME_LABELS[r.outcome],
            causes_text=" · ".join(REASON_LABELS.get(c, c) for c in r.causes),
            known_text=_known_text(r),
            note=r.note,
            verdict=verdict[0] if verdict else None,
            verdict_text=verdict_text,
        )

    by_day: dict[date, list[WorkReport]] = {}
    for r in hit:
        by_day.setdefault(r.work_date, []).append(r)
    days = []
    for day, rows in sorted(by_day.items()):
        stopped = sum(1 for r in rows if r.outcome == "not_done")
        total = per_day.get(day, 0)
        days.append(
            WeatherDay(
                day_text=_long(day),
                entries=tuple(entry(r) for r in rows),
                all_stopped=total > 0 and stopped >= total,
                work_count=total,
            )
        )
    local = now.astimezone(KST)
    return WeatherLogView(
        site_id=site_id,
        site_name=site.name,
        month_text=f"{first.year}년 {first.month}월",
        days=tuple(days),
        affected_days=len(days),
        stopped_days=sum(1 for d in days if d.all_stopped),
        not_done_count=sum(1 for r in hit if r.outcome == "not_done"),
        partial_count=sum(1 for r in hit if r.outcome == "partial"),
        prev_month=f"{(first - timedelta(days=1)):%Y-%m}",
        next_month=f"{_next_month(first):%Y-%m}",
        made_text=f"{_short(local.date())} {local:%H:%M} · {user.display_name}",
    )


def _next_month(first: date) -> date:
    return date(first.year + first.month // 12, first.month % 12 + 1, 1)


def build_change_doc(
    session: Session, user: CurrentUser, site_id: int, case_id: int, kind: ChangeDocKind,
    now: datetime,
) -> ChangeDocView:  # fmt: skip
    """변경 건 상세(권한·열람 기록 포함, changes 서비스)를 그대로 읽어 서류로 보인다."""
    detail = changes_service.build_detail(session, user, case_id, now)
    if detail.site_id != site_id:
        raise HTTPException(status_code=404, detail="변경 건을 찾을 수 없습니다")
    confirmed = next((r for r in detail.revisions if r.status == "confirmed"), None)
    local = now.astimezone(KST)
    return ChangeDocView(
        kind=kind,
        kind_title=CHANGE_DOC_TITLES[kind],
        detail=detail,
        current=confirmed or (detail.revisions[0] if detail.revisions else None),
        confirmed=confirmed is not None,
        made_text=f"{_short(local.date())} {local:%H:%M} · {user.display_name}",
    )


def build_loss_summary(
    session: Session, user: CurrentUser, site_id: int, now: datetime, requested: str
) -> LossSummaryView:
    """작업 차질 월 집계(C14-5, D-113): 원인별 일부만·못함 건수, 적은 인원 합, 언제 알았나.

    원인을 여러 개 고른 기록은 원인마다 세고, 합계 줄은 기록 하나를 한 번만 센다.
    """
    teams_service.require_role(session, user, site_id, ALL_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    first = month_start(now, requested)
    reports = reports_between(session, site_id, first, _next_month(first) - timedelta(days=1))
    short = [r for r in reports if r.outcome != "done"]
    by_cause: dict[str, list[WorkReport]] = {}
    for r in short:
        for c in r.causes:
            by_cause.setdefault(c, []).append(r)
    rows = sorted(
        (_loss_row(REASON_LABELS.get(c, c), group) for c, group in by_cause.items()),
        key=lambda row: (-(row.partial_count + row.not_done_count), row.label),
    )
    local = now.astimezone(KST)
    return LossSummaryView(
        site_id=site_id,
        site_name=site.name,
        month_text=f"{first.year}년 {first.month}월",
        rows=tuple(rows),
        total=_loss_row("합계", short),
        known_headers=(*KNOWN_LABELS.values(), "모름"),
        recorded_count=len(reports),
        prev_month=f"{(first - timedelta(days=1)):%Y-%m}",
        next_month=f"{_next_month(first):%Y-%m}",
        made_text=f"{_short(local.date())} {local:%H:%M} · {user.display_name}",
    )


def _loss_row(label: str, group: list[WorkReport]) -> LossRow:
    codes = (*KNOWN_LABELS, None)
    return LossRow(
        label=label,
        partial_count=sum(1 for r in group if r.outcome == "partial"),
        not_done_count=sum(1 for r in group if r.outcome == "not_done"),
        workers_total=_sum(r.workers for r in group),
        known=tuple(sum(1 for r in group if r.known_when == code) for code in codes),
    )
