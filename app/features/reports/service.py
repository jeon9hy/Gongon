"""변경과 이어진 서류(C14, D-112). 공온에 저장된 기록에서 규칙으로 만든다(LLM 없음).

- 주간 작업계획표(C14-1): 공정회의 자료. 월~일 업체별·요일별 작업, 공온 점검과 같은 기준의 점검,
  판정 범위 안 날의 판정 단계, 그 주 시작 전 7일 동안 확정된 변경, 지금 안 끝난 조치.
- 연락처·메모·담당자 이름은 넣지 않는다. 인쇄·PDF 저장용이며 공식 서류를 대신하지 않는다.
"""

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.actions import service as actions_service
from app.features.auth.schemas import CurrentUser
from app.features.changes import service as changes_service
from app.features.judgments import service as judgments_service
from app.features.reports.schemas import (
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
from app.features.teams.schemas import ALL_ROLES
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

    grouped: dict[int | None, list[WorkItemRecord]] = {}
    for i in items:
        grouped.setdefault(i.performing_participant_id, []).append(i)
    order = [o.participant_id for o in teams_service.participant_choices(session, site_id)]
    # 참여를 끝낸 업체에 남은 작업도 빠뜨리지 않는다(이름 순으로 뒤에)
    ended = sorted((p for p in grouped if p is not None and p not in order),
                   key=lambda p: names.get(p, ""))  # fmt: skip
    rows = [
        WeeklyRow(company=names.get(p, "이름 없음"), cells=cells(grouped[p]))
        for p in (*order, *ended)
        if p in grouped
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


def _short(day: date) -> str:
    return f"{day.month}/{day.day}({_WEEKDAYS[day.weekday()]})"


def _long(day: date) -> str:
    return f"{day.month}월 {day.day}일({_WEEKDAYS[day.weekday()]})"
