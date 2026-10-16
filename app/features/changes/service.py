"""변경 건·버전·확정(C05, collab-contract §4).

- 제안: 조정자·담당자. 작업의 현재 계획을 '변경 전'으로 기록하고 제안할 때의 계획 버전을 남긴다.
- 확정: 조정자만. 계획 갱신(schedules.apply_plan_change_by_id)·이전 확정 버전 대체·이 버전 확정을
  한 트랜잭션으로 저장한다. 하나라도 실패하면 모두 되돌린다. 후속 조치·발송 대기는 C06·C07에서
  같은 트랜잭션에 더한다.
- 같은 확정 요청을 다시 보내면(confirm_key) 같은 결과를 돌려주고 두 번 저장하지 않는다.
- 제안 뒤 작업 계획이 바뀌었으면(다른 변경 확정·작업 수정) 확정하지 않는다.
  새 버전으로 다시 제안한다.
"""

import secrets
from datetime import date, datetime, time
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser, UserInfo
from app.features.changes.models import ChangeCase, ChangeRevision
from app.features.changes.schemas import (
    OPEN_STATUSES,
    REASON_LABELS,
    STATUS_LABELS,
    ChangeDetailView,
    ChangeForm,
    ChangeFormView,
    ChangeListItem,
    ChangesView,
    ReasonOption,
    RevisionView,
    SiteFilter,
)
from app.features.schedules import service as schedules_service
from app.features.schedules.schemas import PlanValues, WorkItemRecord
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteRecord
from app.features.teams import service as teams_service
from app.features.teams.schemas import ALL_ROLES, MANAGE_ROLES, PROPOSE_ROLES
from engine.kst import KST

TITLE_MAX = 80
LOCATION_MAX = 60
LIST_LIMIT = 50  # 목록은 최근 50건. 더 필요하면 페이지 처리를 더한다
_WEEKDAYS = "월화수목금토일"


# ---------- 제안 ----------


def new_form_view(
    session: Session,
    user: CurrentUser,
    site_id: int,
    item_id: int,
    case_id: int | None = None,
    form: ChangeForm | None = None,
    errors: tuple[str, ...] = (),
) -> ChangeFormView:
    teams_service.require_role(session, user, site_id, PROPOSE_ROLES)
    site, item = _site_and_item(session, site_id, item_id)
    if case_id is not None:
        _case_in_site(session, case_id, site_id)
    if form is None:
        form = ChangeForm(
            work_item_id=str(item.item_id),
            case_id="" if case_id is None else str(case_id),
            after_work_date=item.work_date.isoformat(),
            after_start=f"{item.start_local:%H:%M}",
            after_end=f"{item.end_local:%H:%M}",
            after_location=item.location,
            plan_version=str(item.plan_version),
        )
    return ChangeFormView(
        site_id=site.site_id,
        site_name=site.name,
        work_item_id=item.item_id,
        work_label=item.label,
        current_text=_plan_text(item.work_date, item.start_local, item.end_local, item.location),
        plan_version=item.plan_version,
        case_id=case_id,
        form=form,
        reasons=tuple(
            ReasonOption(c, label, c in form.reasons) for c, label in REASON_LABELS.items()
        ),
        errors=errors,
    )


def propose(
    session: Session, user: CurrentUser, site_id: int, form: ChangeForm, today: date, now: datetime
) -> tuple[int | None, tuple[str, ...]]:
    """변경 건(또는 재변경 버전)을 만든다. (변경 건 ID, 오류)."""
    teams_service.require_role(session, user, site_id, PROPOSE_ROLES)
    item_id = _int(form.work_item_id)
    if item_id is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    site, item = _site_and_item(session, site_id, item_id)
    case_id = _int(form.case_id) if form.case_id else None
    case = None if case_id is None else _case_in_site(session, case_id, site_id)
    if case is not None and case.work_item_id != item.item_id:
        raise HTTPException(status_code=404, detail="변경 건을 찾을 수 없습니다")

    errors: list[str] = []
    title = form.title.strip()
    if case is None and not 1 <= len(title) <= TITLE_MAX:
        errors.append(f"변경 제목을 1~{TITLE_MAX}자로 입력하세요.")
    reasons = [r for r in REASON_LABELS if r in form.reasons]
    if not reasons:
        errors.append("변경 원인을 하나 이상 고르세요.")
    elif len(reasons) != len(set(form.reasons)):
        errors.append("목록에 있는 변경 원인을 고르세요.")
    after_date, after_start, after_end = (
        _date(form.after_work_date), _time(form.after_start), _time(form.after_end)
    )  # fmt: skip
    location = form.after_location.strip()
    if after_date is None:
        errors.append("바뀐 작업 날짜를 날짜 형식으로 입력하세요.")
    elif after_date < today:
        errors.append("바뀐 작업 날짜는 오늘 이후여야 합니다.")
    elif not site.works_on(after_date):
        errors.append(f"현장 작업 기간({site.period_text()}) 안의 날짜를 고르세요.")
    if after_start is None or after_end is None:
        errors.append("바뀐 작업 시간을 00:00 형식으로 입력하세요.")
    elif after_start >= after_end:
        errors.append("작업 종료는 시작보다 늦어야 합니다(같은 날 안에서).")
    if len(location) > LOCATION_MAX:
        errors.append(f"작업 위치는 {LOCATION_MAX}자 이하로 입력하세요.")
    if _int(form.plan_version) != item.plan_version:
        errors.append(
            "제안 화면을 연 뒤 작업 계획이 바뀌었습니다. 지금 계획을 확인하고 다시 제안하세요."
        )
    if (after_date, after_start, after_end, location) == (
        item.work_date,
        item.start_local,
        item.end_local,
        item.location,
    ):
        errors.append("바뀐 내용이 없습니다. 날짜·시간·위치 중 무엇이 바뀌는지 입력하세요.")
    if errors or after_date is None or after_start is None or after_end is None:
        return None, tuple(errors)

    if case is None:
        case = ChangeCase(site_id=site_id, work_item_id=item.item_id, title=title,
                          created_by_user_id=user.user_id, created_at=now)  # fmt: skip
        session.add(case)
        session.flush()
    number = (
        session.scalar(
            select(func.max(ChangeRevision.number)).where(ChangeRevision.case_id == case.id)
        )
        or 0
    ) + 1
    review = form.submit == "review"
    session.add(
        ChangeRevision(
            case_id=case.id,
            number=number,
            status="review" if review else "draft",
            reasons=reasons,
            basis_note=form.basis_note.strip(),
            based_on_plan_version=item.plan_version,
            before_work_date=item.work_date,
            before_start_local=item.start_local,
            before_end_local=item.end_local,
            before_location=item.location,
            after_work_date=after_date,
            after_start_local=after_start,
            after_end_local=after_end,
            after_location=location,
            proposed_by_user_id=user.user_id,
            proposed_at=now,
            submitted_at=now if review else None,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        # 같은 건에 진행 중인 버전이 이미 있다(uq_change_revisions_one_open, 동시 제안 포함)
        session.rollback()
        return None, (
            "이 변경 건에 진행 중인 제안이 있습니다. "
            "그 제안을 확정하거나 철회한 뒤 다시 제안하세요.",
        )
    return case.id, ()


# ---------- 상태 전이 ----------

Outcome = Literal["ok", "already"]


def submit(session: Session, user: CurrentUser, site_id: int, case_id: int, revision_id: int,
           now: datetime) -> tuple[str, ...]:  # fmt: skip
    """초안 → 영향 검토. 제안자 본인 또는 조정자."""
    role = teams_service.require_role(session, user, site_id, PROPOSE_ROLES)
    revision = _locked_revision(session, site_id, case_id, revision_id)
    if revision.status != "draft":
        session.rollback()
        return (f"{STATUS_LABELS[revision.status]} 상태라 영향 검토로 보낼 수 없습니다.",)
    if role not in MANAGE_ROLES and revision.proposed_by_user_id != user.user_id:
        session.rollback()
        raise HTTPException(status_code=403, detail=teams_service.FORBIDDEN)
    revision.status = "review"
    revision.submitted_at = now
    session.commit()
    return ()


def confirm(
    session: Session,
    user: CurrentUser,
    site_id: int,
    case_id: int,
    revision_id: int,
    confirm_key: str,
    now: datetime,
) -> tuple[Outcome | None, tuple[str, ...]]:
    """영향 검토 → 확정. 조정자만. 계획 갱신과 이전 확정 버전 대체를 한 트랜잭션으로."""
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    key = confirm_key.strip()[:64]
    if not key:
        return None, ("확정 요청을 확인할 수 없습니다. 화면을 새로 열고 다시 확정하세요.",)
    revision = _locked_revision(session, site_id, case_id, revision_id)
    if revision.status in ("confirmed", "superseded") and revision.confirm_key == key:
        session.rollback()
        return "already", ()  # 같은 요청을 다시 보냄(새로고침·두 번 누름)
    if revision.status != "review":
        session.rollback()
        return None, (f"{STATUS_LABELS[revision.status]} 상태라 확정할 수 없습니다.",)
    case = session.get(ChangeCase, case_id)
    assert case is not None
    item = schedules_service.get_item(session, site_id, case.work_item_id)
    if item is None:
        session.rollback()
        return None, ("작업이 지워져 확정할 수 없습니다.",)
    values = PlanValues(
        work_date=revision.after_work_date,
        start_local=revision.after_start_local,
        end_local=revision.after_end_local,
        location=revision.after_location,
        memo=item.memo,
        performing_participant_id=item.performing_participant_id,
    )
    result = schedules_service.apply_plan_change_by_id(
        session, site_id, item.item_id, revision.based_on_plan_version, values,
        changed_by=user.user_id, now=now, source="change",
    )  # fmt: skip
    if result in ("conflict", "missing"):
        session.rollback()
        return None, (
            "제안 뒤 작업 계획이 바뀌어 확정하지 않았습니다. "
            "이 제안을 철회하고 지금 계획으로 다시 제안하세요.",
        )
    try:
        previous = session.scalars(
            select(ChangeRevision).where(
                ChangeRevision.case_id == case_id, ChangeRevision.status == "confirmed"
            )
        ).all()
        for old in previous:
            old.status = "superseded"
            old.superseded_at = now
        session.flush()  # 현재 확정 버전은 하나(uq_change_revisions_one_current)
        revision.status = "confirmed"
        revision.confirmed_by_user_id = user.user_id
        revision.confirmed_at = now
        revision.confirm_key = key
        _after_confirm(session, revision)
        session.commit()
    except IntegrityError:
        session.rollback()
        return None, ("이미 처리된 확정 요청입니다. 화면을 새로 열어 확인하세요.",)
    return "ok", ()


def _after_confirm(session: Session, revision: ChangeRevision) -> None:
    """확정과 같은 트랜잭션에서 할 일. C06에서 후속 조치 생성, C07에서 발송 대기를 더한다."""
    session.flush()


def withdraw(
    session: Session,
    user: CurrentUser,
    site_id: int,
    case_id: int,
    revision_id: int,
    reason: str,
    now: datetime,
) -> tuple[str, ...]:
    """확정 전 버전을 철회한다(이유 필수). 제안자 본인 또는 조정자.

    확정한 버전은 철회하지 않는다(바꾸려면 재변경).
    """
    role = teams_service.require_role(session, user, site_id, PROPOSE_ROLES)
    revision = _locked_revision(session, site_id, case_id, revision_id)
    if revision.status not in OPEN_STATUSES:
        session.rollback()
        return (
            f"{STATUS_LABELS[revision.status]} 버전은 철회할 수 없습니다. "
            "바꾸려면 재변경을 제안하세요.",
        )
    if role not in MANAGE_ROLES and revision.proposed_by_user_id != user.user_id:
        session.rollback()
        raise HTTPException(status_code=403, detail=teams_service.FORBIDDEN)
    if not reason.strip():
        session.rollback()
        return ("철회 이유를 입력하세요.",)
    revision.status = "withdrawn"
    revision.withdrawn_by_user_id = user.user_id
    revision.withdrawn_at = now
    revision.withdraw_reason = reason.strip()
    session.commit()
    return ()


# ---------- 화면 ----------


def build_list(
    session: Session, scope: frozenset[int], site_id: int | None, show: Literal["open", "all"]
) -> ChangesView | None:
    sites = sites_service.list_sites(session, scope)
    if site_id is not None and site_id not in {s.site_id for s in sites}:
        return None
    site_ids = [site_id] if site_id is not None else [s.site_id for s in sites]
    latest = (
        select(ChangeRevision.case_id, func.max(ChangeRevision.number).label("number"))
        .group_by(ChangeRevision.case_id)
        .subquery()
    )
    query = (
        select(ChangeCase, ChangeRevision)
        .join(latest, latest.c.case_id == ChangeCase.id)
        .join(
            ChangeRevision,
            (ChangeRevision.case_id == ChangeCase.id) & (ChangeRevision.number == latest.c.number),
        )
        .where(ChangeCase.site_id.in_(site_ids))
        .order_by(ChangeCase.id.desc())
        .limit(LIST_LIMIT)
    )
    if show == "open":
        query = query.where(ChangeRevision.status.in_(OPEN_STATUSES))
    rows = session.execute(query).all() if site_ids else []
    labels = _work_labels(session, [c.work_item_id for c, _ in rows])
    base = "/changes" + ("" if site_id is None else f"?site_id={site_id}")
    joiner = "&" if site_id is not None else "?"
    return ChangesView(
        sites=tuple(SiteFilter(s.site_id, s.name, s.site_id == site_id) for s in sites),
        site_id=site_id,
        show=show,
        items=tuple(
            ChangeListItem(
                href=f"/changes/{case.id}",
                title=case.title,
                work_label=labels.get(case.work_item_id, "지운 작업"),
                status=rev.status,
                status_label=STATUS_LABELS[rev.status],
                version_text=f"v{rev.number}",
                after_text=_plan_text(
                    rev.after_work_date,
                    rev.after_start_local,
                    rev.after_end_local,
                    rev.after_location,
                ),
                reasons_text=", ".join(REASON_LABELS[r] for r in rev.reasons),
                updated_text=f"{_last_event(rev).astimezone(KST):%m/%d %H:%M}",
            )
            for case, rev in rows
        ),
        open_href=base,
        all_href=f"{base}{joiner}show=all",
    )


def build_detail(
    session: Session,
    user: CurrentUser,
    case_id: int,
    errors: tuple[str, ...] = (),
    message: str | None = None,
) -> ChangeDetailView:
    case = session.get(ChangeCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="변경 건을 찾을 수 없습니다")
    role = teams_service.require_role(session, user, case.site_id, ALL_ROLES)
    site = sites_service.get_site(session, case.site_id, None)
    if site is None:
        raise HTTPException(status_code=404, detail="변경 건을 찾을 수 없습니다")
    revisions = list(
        session.scalars(
            select(ChangeRevision)
            .where(ChangeRevision.case_id == case_id)
            .order_by(ChangeRevision.number.desc())
        )
    )
    people = auth_service.describe_users(session, _people(revisions))
    item = schedules_service.get_item(session, case.site_id, case.work_item_id)
    current = next((r for r in revisions if r.status == "confirmed"), None)
    has_open = any(r.status in OPEN_STATUSES for r in revisions)
    can_propose = role in PROPOSE_ROLES and item is not None
    return ChangeDetailView(
        case_id=case.id,
        site_id=case.site_id,
        site_name=site.name,
        title=case.title,
        work_label="지운 작업" if item is None else item.label,
        current_plan_text="작업이 지워졌습니다"
        if item is None
        else f"{_plan_text(item.work_date, item.start_local, item.end_local, item.location)}"
        f" · 계획 v{item.plan_version}",
        current_version_text=None if current is None else f"v{current.number}",
        revisions=tuple(_revision_view(r, role, user, people) for r in revisions),
        rechange_href=None
        if has_open or not can_propose
        else f"/changes/new?site_id={case.site_id}&item_id={case.work_item_id}&case_id={case.id}",
        confirm_key=secrets.token_urlsafe(24),
        errors=errors,
        message=message,
    )


def _revision_view(
    r: ChangeRevision, role: str, user: CurrentUser, people: dict[int, UserInfo]
) -> RevisionView:
    def name(user_id: int | None) -> str:
        info = people.get(user_id or -1)
        return "알 수 없음" if info is None else info.display_name

    def when(at: datetime) -> str:
        return f"{at.astimezone(KST):%m/%d %H:%M}"

    history = [f"{when(r.proposed_at)} 제안 · {name(r.proposed_by_user_id)}"]
    if r.submitted_at is not None:
        history.append(f"{when(r.submitted_at)} 영향 검토로 보냄")
    if r.confirmed_at is not None:
        history.append(f"{when(r.confirmed_at)} 확정 · {name(r.confirmed_by_user_id)}")
    if r.superseded_at is not None:
        history.append(f"{when(r.superseded_at)} 다음 버전 확정으로 대체됨")
    if r.withdrawn_at is not None:
        history.append(f"{when(r.withdrawn_at)} 철회 · {name(r.withdrawn_by_user_id)}")
    mine = r.proposed_by_user_id == user.user_id
    manage = role in MANAGE_ROLES
    return RevisionView(
        revision_id=r.id,
        number=r.number,
        status=r.status,
        status_label=STATUS_LABELS[r.status],
        before_text=_plan_text(r.before_work_date, r.before_start_local, r.before_end_local,
                               r.before_location) + f" · 계획 v{r.based_on_plan_version}",
        after_text=_plan_text(r.after_work_date, r.after_start_local, r.after_end_local,
                              r.after_location),
        reasons_text=", ".join(REASON_LABELS[c] for c in r.reasons),
        basis_note=r.basis_note,
        history=tuple(history),
        withdraw_reason=r.withdraw_reason,
        can_submit=r.status == "draft" and (manage or mine),
        can_confirm=r.status == "review" and manage,
        can_withdraw=r.status in OPEN_STATUSES and (manage or mine),
    )  # fmt: skip


# ---------- 내부 ----------


def _site_and_item(
    session: Session, site_id: int, item_id: int
) -> tuple[SiteRecord, WorkItemRecord]:
    site = sites_service.get_site(session, site_id, None)
    item = schedules_service.get_item(session, site_id, item_id)
    if site is None or item is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    return site, item


def _case_in_site(session: Session, case_id: int, site_id: int) -> ChangeCase:
    case = session.get(ChangeCase, case_id)
    if case is None or case.site_id != site_id:
        raise HTTPException(status_code=404, detail="변경 건을 찾을 수 없습니다")
    return case


def _locked_revision(
    session: Session, site_id: int, case_id: int, revision_id: int
) -> ChangeRevision:
    """같은 버전을 동시에 확정·철회하지 않게 행을 잠그고 읽는다. 다른 현장·건이면 404."""
    revision = session.scalar(
        select(ChangeRevision)
        .join(ChangeCase, ChangeCase.id == ChangeRevision.case_id)
        .where(
            ChangeRevision.id == revision_id,
            ChangeRevision.case_id == case_id,
            ChangeCase.site_id == site_id,
        )
        .with_for_update(of=ChangeRevision)
    )
    if revision is None:
        session.rollback()
        raise HTTPException(status_code=404, detail="변경 버전을 찾을 수 없습니다")
    return revision


def _work_labels(session: Session, item_ids: list[int]) -> dict[int, str]:
    """목록의 작업 이름(쿼리 1회, 반복 조회 없음)."""
    return {i: r.label for i, r in schedules_service.items_by_ids(session, item_ids).items()}


def _people(revisions: list[ChangeRevision]) -> set[int]:
    ids: set[int] = set()
    for r in revisions:
        ids |= {i for i in (r.proposed_by_user_id, r.confirmed_by_user_id,
                            r.withdrawn_by_user_id) if i is not None}  # fmt: skip
    return ids


def _last_event(r: ChangeRevision) -> datetime:
    return max(t for t in (r.proposed_at, r.submitted_at, r.confirmed_at, r.withdrawn_at,
                           r.superseded_at) if t is not None)  # fmt: skip


def _plan_text(day: date, start: time, end: time, location: str) -> str:
    place = f" · {location}" if location else ""
    return f"{day:%m/%d}({_WEEKDAYS[day.weekday()]}) {start:%H:%M}-{end:%H:%M}{place}"


def _int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def _date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _time(raw: str) -> time | None:
    try:
        return time.fromisoformat(raw.strip())
    except ValueError:
        return None
