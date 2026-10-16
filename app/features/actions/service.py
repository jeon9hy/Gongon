"""후속 조치·처리 기록·검증·위임(C06, collab-contract §5).

변경 기능(changes)이 버전 상태를 확인한 뒤 이 서비스를 부른다. 여기서는 커밋하지 않는다.
변경 확정·조치 처리·종료는 changes 서비스가 한 트랜잭션으로 저장한다(architecture §7).

- 후보: 영향 검토 중인 버전에 붙인다. 확정 때 requested가 되며 그 뒤에는 내용을 고치지 않는다.
- 수행자: 지정 담당자, 담당 미지정이면 실행 업체의 조정자·담당자, 그리고 위임받은 사람.
  조정자는 수행자 대신 전화로 확인한 내용을 기록할 수 있다(연락 상대·시각 필수, 대리 기록 표시).
- 검증자는 완료 보고자와 다르다(A3). 검증자는 같은 조치를 완료 보고할 수 없다.
- 필수 조치는 지우지 않는다. 빼려면 조정자가 이유와 함께 제외한다.
"""

from collections.abc import Callable, Iterable
from datetime import date, datetime, time

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.features.actions.models import ActionDelegation, ActionEvent, ActionItem
from app.features.actions.schemas import (
    ACTION_KINDS,
    EVENT_LABELS,
    OPEN_STATUSES,
    STATUS_LABELS,
    UNSTARTED_STATUSES,
    ActionCard,
    ActionForm,
    CandidateEditor,
    CandidateForm,
    DelegateChoice,
    DelegationRow,
    MyActionItem,
    MyActionsView,
    Option,
    PerformerMode,
    RevisionActions,
)
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser
from app.features.sites import service as sites_service
from app.features.teams import service as teams_service
from app.features.teams.schemas import ACTION_ROLES, MANAGE_ROLES, SiteMember
from engine.kst import KST

TITLE_MAX = 80
TEXT_MAX = 1000
SHORT_MAX = 100
RESOLVER_MAX = 60
CANDIDATES_MAX = 30  # 버전 하나의 조치 수 상한
MY_LIST_LIMIT = 100
SUGGESTIONS = 20
_WEEKDAYS = "월화수목금토일"


# ---------- 후보(영향 검토) ----------


def add_candidate(
    session: Session,
    user: CurrentUser,
    site_id: int,
    case_id: int,
    revision_id: int,
    form: CandidateForm,
    now: datetime,
) -> tuple[str, ...]:
    """조치 후보를 더한다. 버전이 열려 있는지와 편집 권한은 changes가 먼저 확인한다."""
    members = {m.user_id: m for m in teams_service.site_members(session, site_id)}
    participants = teams_service.participant_labels(session, site_id)
    errors: list[str] = []
    title = form.title.strip()
    if not 1 <= len(title) <= TITLE_MAX:
        errors.append(f"조치 이름을 1~{TITLE_MAX}자로 입력하세요.")
    participant_id = _int(form.performing_participant_id)
    if participant_id not in participants:
        errors.append("수행 업체를 이 현장의 참여 업체 중에서 고르세요.")
    assignee_id = _int(form.assignee_user_id) if form.assignee_user_id else None
    if assignee_id is not None:
        assignee = members.get(assignee_id)
        if assignee is None or assignee.role not in ACTION_ROLES:
            errors.append("담당자는 이 현장의 조정자·담당자 중에서 고르세요.")
        elif assignee.participant_id != participant_id:
            errors.append("담당자는 수행 업체 소속이어야 합니다.")
    verifier_id = _int(form.verifier_user_id)
    verifier = members.get(verifier_id or -1)
    if verifier is None or verifier.role not in ACTION_ROLES:
        errors.append("검증자를 이 현장의 조정자·담당자 중에서 고르세요.")
    elif verifier_id == assignee_id:
        errors.append("검증자는 담당자와 다른 사람이어야 합니다.")
    due_at, due_error = _due(form)
    if due_error:
        errors.append(due_error)
    count = session.scalar(
        select(func.count()).select_from(ActionItem).where(ActionItem.revision_id == revision_id)
    )
    if (count or 0) >= CANDIDATES_MAX:
        errors.append(f"한 버전의 조치는 {CANDIDATES_MAX}건까지입니다.")
    if errors or participant_id is None or verifier_id is None:
        return tuple(errors)
    session.add(
        ActionItem(
            case_id=case_id,
            revision_id=revision_id,
            site_id=site_id,
            title=title,
            performing_participant_id=participant_id,
            assignee_user_id=assignee_id,
            verifier_user_id=verifier_id,
            required=form.required,
            due_at=due_at,
            due_note=None if due_at else form.due_note.strip(),
            status="candidate",
            created_by_user_id=user.user_id,
            created_at=now,
        )
    )
    session.flush()
    return ()


def remove_candidate(session: Session, revision_id: int, action_id: int) -> bool:
    """확정 전 후보만 지운다. 확정한 조치는 지우지 않고 제외한다."""
    action = session.get(ActionItem, action_id)
    if action is None or action.revision_id != revision_id or action.status != "candidate":
        return False
    session.delete(action)
    session.flush()
    return True


def activate(
    session: Session, site_id: int, revision_id: int, actor_id: int, now: datetime
) -> tuple[int, tuple[str, ...]]:
    """확정과 같은 트랜잭션에서 후보를 요청으로 바꾼다. (필수 조치 수, 오류).

    후보를 만든 뒤 담당·검증자의 참여가 회수됐으면 확정하지 않는다.
    """
    candidates = list(
        session.scalars(
            select(ActionItem)
            .where(ActionItem.revision_id == revision_id, ActionItem.status == "candidate")
            .order_by(ActionItem.id)
            .with_for_update()
        )
    )
    members = {m.user_id: m for m in teams_service.site_members(session, site_id)}
    errors: list[str] = []
    for a in candidates:
        assignee = members.get(a.assignee_user_id or -1)
        verifier = members.get(a.verifier_user_id)
        if a.assignee_user_id is not None and (
            assignee is None or assignee.role not in ACTION_ROLES
        ):
            errors.append(f"‘{a.title}’ 담당자가 더 이상 이 현장의 담당자가 아닙니다.")
        if verifier is None or verifier.role not in ACTION_ROLES:
            errors.append(f"‘{a.title}’ 검증자가 더 이상 이 현장의 담당자가 아닙니다.")
    if errors:
        return 0, tuple(errors)
    for a in candidates:
        a.status = "requested"
        session.add(_event(a, "requested", actor_id, now))
    session.flush()
    return sum(1 for a in candidates if a.required), ()


def replace_unstarted(
    session: Session, revision_ids: Iterable[int], actor_id: int, now: datetime
) -> int:
    """재변경 확정 때 이전 버전의 아직 끝나지 않은 조치(요청·수행 중·막힘)를 대체됨으로 둔다.

    완료 보고·검증한 조치는 그대로 남긴다. 새 조치와의 연결·보완 후보는 C07에서 더한다.
    """
    ids = list(revision_ids)
    if not ids:
        return 0
    old = list(
        session.scalars(
            select(ActionItem)
            .where(ActionItem.revision_id.in_(ids), ActionItem.status.in_(UNSTARTED_STATUSES))
            .with_for_update()
        )
    )
    for a in old:
        a.status = "replaced"
        session.add(_event(a, "replaced", actor_id, now))
    session.flush()
    return len(old)


# ---------- 처리 ----------


def act(
    session: Session,
    user: CurrentUser,
    site_id: int,
    case_id: int,
    action_id: int,
    kind: str,
    form: ActionForm,
    now: datetime,
) -> tuple[str, ...]:
    """조치 하나를 처리한다. 다른 현장·건의 조치는 404, 권한이 없으면 403."""
    if kind not in ACTION_KINDS:
        raise HTTPException(status_code=404, detail="처리를 찾을 수 없습니다")
    action = session.scalar(
        select(ActionItem)
        .where(
            ActionItem.id == action_id,
            ActionItem.case_id == case_id,
            ActionItem.site_id == site_id,
        )
        .with_for_update()
    )
    if action is None or action.status == "candidate":
        raise HTTPException(status_code=404, detail="조치를 찾을 수 없습니다")
    if _int(form.revision_id) != action.revision_id or action.status == "replaced":
        return ("이전 버전의 조치입니다. 화면을 새로 열고 현재 버전의 조치를 처리하세요.",)
    me = next(
        (m for m in teams_service.site_members(session, site_id) if m.user_id == user.user_id),
        None,
    )
    if me is None:
        raise HTTPException(status_code=404, detail="조치를 찾을 수 없습니다")
    delegators = _delegators(session, site_id, user.user_id, now)
    mode = _performer_mode(action, me, delegators)
    allowed = _allowed(action, me, mode)
    if kind not in allowed:
        if not _possible(action.status, kind):
            return (f"{STATUS_LABELS[action.status]} 상태라 이 처리를 할 수 없습니다.",)
        if kind == "report" and action.verifier_user_id == user.user_id:
            return ("검증자는 같은 조치를 완료 보고할 수 없습니다. 수행자가 보고하게 하세요.",)
        if kind == "verify" and action.reported_by_user_id == user.user_id:
            return ("완료 보고한 사람은 같은 조치를 검증할 수 없습니다.",)
        raise HTTPException(status_code=403, detail=teams_service.FORBIDDEN)

    body = form.body.strip()
    counterpart, reference = form.counterpart.strip(), form.reference.strip()
    errors: list[str] = []
    if len(body) > TEXT_MAX:
        errors.append(f"내용은 {TEXT_MAX}자 이하로 입력하세요.")
    if len(counterpart) > SHORT_MAX or len(reference) > SHORT_MAX:
        errors.append(f"연락 상대·참조 번호는 {SHORT_MAX}자 이하로 입력하세요.")
    behalf = kind in ("accept", "resume", "block", "report") and mode == "behalf"
    contacted_at = _local(form.contacted_date, form.contacted_time)
    if kind == "phone" or behalf:
        if not counterpart:
            errors.append("연락한 상대와 회사를 입력하세요(예: 김OO · 가상펌프).")
        if contacted_at is None:
            errors.append("연락한 날짜와 시각을 입력하세요.")
        elif contacted_at > now:
            errors.append("연락 시각은 지금보다 늦을 수 없습니다.")
        if kind == "phone" and not body:
            errors.append("통화 내용을 입력하세요.")
    performed_at = None
    if kind == "report":
        performed_at = _local(form.performed_date, form.performed_time)
        if not body:
            errors.append("처리 내용을 입력하세요(무엇을 누구와 어떻게 바꿨는지).")
        if performed_at is None:
            errors.append("실제 처리한 날짜와 시각을 입력하세요.")
        elif performed_at > now:
            errors.append("처리 시각은 지금보다 늦을 수 없습니다.")
    if kind == "block":
        if not body:
            errors.append("막힌 이유를 입력하세요.")
        if not form.resolver.strip():
            errors.append("막힘을 풀 담당(사람·회사)을 입력하세요.")
        elif len(form.resolver.strip()) > RESOLVER_MAX:
            errors.append(f"막힘을 풀 담당은 {RESOLVER_MAX}자 이하로 입력하세요.")
    if kind in ("reject", "exclude") and not body:
        errors.append("반려 이유를 입력하세요." if kind == "reject" else "제외 이유를 입력하세요.")
    if errors:
        session.rollback()
        return tuple(errors)

    event_kind = {
        "accept": "accepted",
        "resume": "resumed",
        "block": "blocked",
        "report": "reported",
        "verify": "verified",
        "reject": "rejected",
        "exclude": "excluded",
        "phone": "phone_record",
    }[kind]
    if kind in ("accept", "resume", "reject"):
        action.status = "accepted"
    elif kind == "block":
        action.status = "blocked"
        action.blocked_reason = body
        action.blocked_resolver = form.resolver.strip()
    elif kind == "report":
        action.status = "reported"
        action.reported_by_user_id = user.user_id
        action.reported_at = now
        action.performed_at = performed_at
    elif kind == "verify":
        action.status = "verified"
        action.verified_by_user_id = user.user_id
        action.verified_at = now
    elif kind == "exclude":
        action.status = "excluded"
        action.excluded_by_user_id = user.user_id
        action.excluded_at = now
        action.exclude_reason = body
    if kind == "reject":
        # 반려하면 다시 수행 중. 이전 보고는 사건 기록에 남고 검증 대상이 아니다.
        action.reported_by_user_id = None
        action.reported_at = None
        action.performed_at = None
    if kind in ("accept", "resume"):
        action.blocked_reason = None
        action.blocked_resolver = None
    event = _event(action, event_kind, user.user_id, now)
    event.body = body
    event.counterpart = counterpart
    event.reference = reference
    event.performed_at = performed_at
    if kind == "phone" or behalf:
        event.contacted_at = contacted_at
    event.on_behalf = behalf
    if mode == "delegate" and kind in ("accept", "resume", "block", "report"):
        event.delegated_from_user_id = action.assignee_user_id
    session.add(event)
    session.flush()
    return ()


def closure_problems(session: Session, revision_id: int) -> tuple[int, tuple[str, ...]]:
    """종료 조건(§1.2-5). 현재 확정 버전의 조치를 잠그고 확인한다. (필수 조치 수, 남은 문제).

    변경 건 행 잠금은 changes가 먼저 한다(확정과 종료가 동시에 일어나지 않게).
    """
    actions = list(
        session.scalars(
            select(ActionItem)
            .where(ActionItem.revision_id == revision_id, ActionItem.status != "candidate")
            .with_for_update()
        )
    )
    required = [a for a in actions if a.required]
    problems: list[str] = []
    waiting = [a for a in required if a.status not in ("verified", "excluded")]
    if waiting:
        problems.append(f"필수 조치 {len(waiting)}건이 아직 검증 완료되지 않았습니다.")
    blocked = [a for a in actions if a.status == "blocked"]
    if blocked:
        problems.append(f"막힌 조치 {len(blocked)}건이 해결되지 않았습니다.")
    return len(required), tuple(problems)


# ---------- 위임 ----------


def add_delegation(
    session: Session,
    user: CurrentUser,
    choice: str,
    start_date: str,
    start_time: str,
    end_date: str,
    end_time: str,
    now: datetime,
) -> tuple[str, ...]:
    """내 조치를 같은 현장·같은 업체의 다른 조정자·담당자에게 기간을 정해 맡긴다."""
    site_part, _, to_part = choice.partition(":")
    site_id, to_user_id = _int(site_part), _int(to_part)
    if site_id is None or to_user_id is None:
        return ("맡길 사람을 고르세요.",)
    members = {m.user_id: m for m in teams_service.site_members(session, site_id)}
    me, target = members.get(user.user_id), members.get(to_user_id)
    if me is None:
        raise HTTPException(status_code=404, detail=teams_service.NOT_FOUND)
    errors: list[str] = []
    if target is None or target.role not in ACTION_ROLES or target.user_id == user.user_id:
        errors.append("같은 현장의 다른 조정자·담당자를 고르세요.")
    elif target.participant_id != me.participant_id:
        errors.append("위임은 같은 업체 사람에게만 할 수 있습니다.")
    starts_at, ends_at = _local(start_date, start_time), _local(end_date, end_time)
    if starts_at is None or ends_at is None:
        errors.append("위임 시작·끝 날짜와 시각을 입력하세요.")
    elif starts_at >= ends_at:
        errors.append("위임 끝은 시작보다 늦어야 합니다.")
    elif ends_at <= now:
        errors.append("이미 지난 기간은 위임할 수 없습니다.")
    if errors or starts_at is None or ends_at is None:
        return tuple(errors)
    session.add(
        ActionDelegation(
            site_id=site_id,
            from_user_id=user.user_id,
            to_user_id=to_user_id,
            starts_at=starts_at,
            ends_at=ends_at,
            created_by_user_id=user.user_id,
            created_at=now,
        )
    )
    session.commit()
    return ()


def revoke_delegation(
    session: Session, user: CurrentUser, delegation_id: int, now: datetime
) -> tuple[str, ...]:
    """위임한 본인 또는 그 현장 조정자가 회수한다. 행은 남긴다."""
    delegation = session.get(ActionDelegation, delegation_id, with_for_update=True)
    if delegation is None:
        raise HTTPException(status_code=404, detail="위임을 찾을 수 없습니다")
    role = teams_service.role_on(session, user.user_id, delegation.site_id)
    if role is None:
        raise HTTPException(status_code=404, detail="위임을 찾을 수 없습니다")
    if delegation.from_user_id != user.user_id and role not in MANAGE_ROLES:
        raise HTTPException(status_code=403, detail=teams_service.FORBIDDEN)
    if delegation.revoked_at is not None:
        session.rollback()
        return ("이미 회수한 위임입니다.",)
    delegation.revoked_at = now
    delegation.revoked_by_user_id = user.user_id
    session.commit()
    return ()


# ---------- 화면 ----------


def revision_actions(
    session: Session,
    user: CurrentUser,
    site_id: int,
    revision_ids: list[int],
    editable: dict[int, bool],
    default_participant_id: int | None,
    now: datetime,
    candidate_form: CandidateForm | None = None,
    candidate_errors: tuple[str, ...] = (),
    candidate_revision_id: int | None = None,
) -> dict[int, RevisionActions]:
    """변경 건 화면의 버전별 조치(조치 1회·사건 1회·사람 2회 조회).

    editable[revision_id]가 참이면 그 버전에 후보 입력 칸을 붙인다(영향 검토 중·편집 권한).
    """
    actions = (
        list(
            session.scalars(
                select(ActionItem)
                .where(ActionItem.revision_id.in_(revision_ids))
                .order_by(ActionItem.id)
            )
        )
        if revision_ids
        else []
    )
    events: dict[int, list[ActionEvent]] = {}
    if actions:
        for e in session.scalars(
            select(ActionEvent)
            .where(ActionEvent.action_id.in_([a.id for a in actions]))
            .order_by(ActionEvent.id)
        ):
            events.setdefault(e.action_id, []).append(e)
    members = teams_service.site_members(session, site_id)
    me = next((m for m in members if m.user_id == user.user_id), None)
    people_ids = {m.user_id for m in members}
    for a in actions:
        people_ids |= {i for i in (a.assignee_user_id, a.verifier_user_id) if i is not None}
    for evs in events.values():
        people_ids |= {e.actor_user_id for e in evs}
        people_ids |= {e.delegated_from_user_id for e in evs if e.delegated_from_user_id}
    names = {
        u.user_id: u.display_name for u in auth_service.describe_users(session, people_ids).values()
    }
    participants = teams_service.participant_labels(session, site_id)
    delegators = _delegators(session, site_id, user.user_id, now)
    suggestions: tuple[str, ...] = ()
    if any(editable.values()):
        suggestions = tuple(
            session.scalars(
                select(ActionItem.title)
                .where(ActionItem.site_id == site_id)
                .group_by(ActionItem.title)
                .order_by(func.max(ActionItem.id).desc())
                .limit(SUGGESTIONS)
            )
        )
    result: dict[int, RevisionActions] = {}
    for revision_id in revision_ids:
        mine = [a for a in actions if a.revision_id == revision_id]
        cards = tuple(
            _card(
                a,
                events.get(a.id, []),
                me,
                delegators,
                names,
                participants,
                now,
                removable=editable.get(revision_id, False),
            )
            for a in mine
        )
        live = [a for a in mine if a.required and a.status not in ("candidate", "replaced")]
        editor = None
        if editable.get(revision_id, False):
            form = (
                candidate_form
                if candidate_form is not None and candidate_revision_id == revision_id
                else CandidateForm(
                    performing_participant_id=""
                    if default_participant_id is None
                    else str(default_participant_id)
                )
            )
            editor = _editor(
                members,
                participants,
                form,
                suggestions,
                candidate_errors if candidate_revision_id == revision_id else (),
            )
        result[revision_id] = RevisionActions(
            cards=cards,
            required_total=len(live),
            required_done=sum(1 for a in live if a.status in ("verified", "excluded")),
            blocked=sum(1 for a in mine if a.status == "blocked"),
            editor=editor,
        )
    return result


def build_my_actions(
    session: Session,
    user: CurrentUser,
    now: datetime,
    errors: tuple[str, ...] = (),
    message: str | None = None,
) -> MyActionsView:
    """내가 처리하거나 검증할 열린 조치(참여 중인 현장만)와 내 위임."""
    memberships = teams_service.memberships_of(session, user.user_id)
    site_ids = [m.site_id for m in memberships]
    sites = {s.site_id: s.name for s in sites_service.list_sites(session, frozenset(site_ids))}
    delegations = (
        list(
            session.scalars(
                select(ActionDelegation)
                .where(
                    ActionDelegation.site_id.in_(site_ids),
                    ActionDelegation.revoked_at.is_(None),
                    ActionDelegation.ends_at > now,
                    or_(
                        ActionDelegation.from_user_id == user.user_id,
                        ActionDelegation.to_user_id == user.user_id,
                    ),
                )
                .order_by(ActionDelegation.starts_at)
            )
        )
        if site_ids
        else []
    )
    delegated_from = {
        (d.site_id, d.from_user_id)
        for d in delegations
        if d.to_user_id == user.user_id and d.starts_at <= now
    }
    performer_participants = [
        (m.site_id, m.participant_id) for m in memberships if m.role in ACTION_ROLES
    ]
    conditions = [
        ActionItem.assignee_user_id == user.user_id,
        ActionItem.verifier_user_id == user.user_id,
    ]
    conditions += [
        (ActionItem.site_id == s) & (ActionItem.assignee_user_id == f) for s, f in delegated_from
    ]
    conditions += [
        (ActionItem.site_id == s)
        & (ActionItem.performing_participant_id == p)
        & ActionItem.assignee_user_id.is_(None)
        for s, p in performer_participants
    ]
    actions = (
        list(
            session.scalars(
                select(ActionItem)
                .where(
                    ActionItem.site_id.in_(site_ids),
                    ActionItem.status.in_(OPEN_STATUSES),
                    or_(*conditions),
                )
                .order_by(ActionItem.due_at.asc().nulls_last(), ActionItem.id)
                .limit(MY_LIST_LIMIT)
            )
        )
        if site_ids
        else []
    )
    to_do: list[MyActionItem] = []
    to_verify: list[MyActionItem] = []
    for a in actions:
        due_text, overdue = _due_text(a, now)

        def item(
            why: str, a: ActionItem = a, due_text: str = due_text, overdue: bool = overdue
        ) -> MyActionItem:
            return MyActionItem(
                href=f"/changes/{a.case_id}#action-{a.id}",
                title=a.title,
                site_name=sites.get(a.site_id, ""),
                status_label=STATUS_LABELS[a.status],
                due_text=due_text,
                overdue=overdue,
                why=why,
            )

        if a.status == "reported" and a.verifier_user_id == user.user_id:
            to_verify.append(item("검증"))
        elif a.status in UNSTARTED_STATUSES and a.verifier_user_id != user.user_id:
            delegated = a.assignee_user_id not in (None, user.user_id)
            to_do.append(item("위임받음" if delegated else "처리"))
    people_ids = {d.from_user_id for d in delegations} | {d.to_user_id for d in delegations}
    choices: list[DelegateChoice] = []
    for site_id in site_ids:
        members = teams_service.site_members(session, site_id)
        me = next((m for m in members if m.user_id == user.user_id), None)
        if me is None or me.role not in ACTION_ROLES:
            continue
        for m in members:
            if (
                m.user_id != user.user_id
                and m.participant_id == me.participant_id
                and m.role in ACTION_ROLES
            ):
                choices.append(
                    DelegateChoice(
                        f"{site_id}:{m.user_id}", f"{sites.get(site_id, '')} · {m.display_name}"
                    )
                )
    names = {
        u.user_id: u.display_name for u in auth_service.describe_users(session, people_ids).values()
    }
    manage = {m.site_id for m in memberships if m.role in MANAGE_ROLES}
    return MyActionsView(
        to_do=tuple(to_do),
        to_verify=tuple(to_verify),
        delegations=tuple(
            DelegationRow(
                delegation_id=d.id,
                site_name=sites.get(d.site_id, ""),
                from_name=names.get(d.from_user_id, "알 수 없음"),
                to_name=names.get(d.to_user_id, "알 수 없음"),
                period_text=f"{_when(d.starts_at)} ~ {_when(d.ends_at)}",
                can_revoke=d.from_user_id == user.user_id or d.site_id in manage,
            )
            for d in delegations
        ),
        delegate_choices=tuple(choices),
        errors=errors,
        message=message,
    )


# ---------- 내부 ----------


def _performer_mode(
    action: ActionItem, me: SiteMember, delegators: set[int]
) -> PerformerMode | None:
    if me.role in ACTION_ROLES and (
        action.assignee_user_id == me.user_id
        or (
            action.assignee_user_id is None
            and me.participant_id == action.performing_participant_id
        )
    ):
        return "self"
    if (
        action.assignee_user_id is not None
        and action.assignee_user_id in delegators
        and me.role in ACTION_ROLES
    ):
        return "delegate"
    if me.role in MANAGE_ROLES:
        return "behalf"
    return None


_POSSIBLE: dict[str, tuple[str, ...]] = {
    "requested": ("accept", "block", "exclude", "phone"),
    "accepted": ("report", "block", "exclude", "phone"),
    "blocked": ("resume", "exclude", "phone"),
    "reported": ("verify", "reject", "exclude", "phone"),
}


def _possible(status: str, kind: str) -> bool:
    return kind in _POSSIBLE.get(status, ())


def _allowed(
    action: ActionItem, me: SiteMember | None, mode: PerformerMode | None
) -> frozenset[str]:
    if me is None:
        return frozenset()
    allowed: set[str] = set()
    for kind in _POSSIBLE.get(action.status, ()):
        if kind in ("accept", "resume", "block", "report"):
            ok = mode is not None
            if kind == "report":
                ok = ok and action.verifier_user_id != me.user_id
        elif kind in ("verify", "reject"):
            ok = action.verifier_user_id == me.user_id and action.reported_by_user_id != me.user_id
        elif kind == "exclude":
            ok = me.role in MANAGE_ROLES
        else:  # phone: 수행자·조정자·검증자
            ok = mode is not None or action.verifier_user_id == me.user_id
        if ok:
            allowed.add(kind)
    return frozenset(allowed)


def _delegators(session: Session, site_id: int, user_id: int, now: datetime) -> set[int]:
    """지금 나에게 수행을 맡긴 사람들(기간 안·회수 안 됨)."""
    return set(
        session.scalars(
            select(ActionDelegation.from_user_id).where(
                ActionDelegation.site_id == site_id,
                ActionDelegation.to_user_id == user_id,
                ActionDelegation.revoked_at.is_(None),
                ActionDelegation.starts_at <= now,
                ActionDelegation.ends_at > now,
            )
        )
    )


def _card(
    a: ActionItem,
    events: list[ActionEvent],
    me: SiteMember | None,
    delegators: set[int],
    names: dict[int, str],
    participants: dict[int, str],
    now: datetime,
    removable: bool,
) -> ActionCard:
    def name(user_id: int | None) -> str:
        return names.get(user_id or -1, "알 수 없음")

    company = participants.get(a.performing_participant_id, "알 수 없는 업체").split(" · ")[0]
    mode = None if me is None else _performer_mode(a, me, delegators)
    allowed = set(_allowed(a, me, mode))
    if removable and a.status == "candidate":
        allowed.add("remove")
    due_text, overdue = _due_text(a, now)
    late = None
    if a.performed_at is not None and a.due_at is not None and a.performed_at > a.due_at:
        late = f"기한 뒤 처리 · 기한 {_when(a.due_at)}, 처리 {_when(a.performed_at)}"
    report = None
    if a.status in ("reported", "verified") and a.performed_at is not None:
        last = next((e for e in reversed(events) if e.kind == "reported"), None)
        detail = "" if last is None else f" · {last.body}"
        report = f"{_when(a.performed_at)} 처리 · {name(a.reported_by_user_id)} 보고{detail}"
    return ActionCard(
        action_id=a.id,
        revision_id=a.revision_id,
        title=a.title,
        status=a.status,
        status_label=STATUS_LABELS[a.status],
        required=a.required,
        performer_text=f"{company} · "
        + (
            "담당 미지정(업체 담당자 누구나)"
            if a.assignee_user_id is None
            else name(a.assignee_user_id)
        ),
        verifier_text=name(a.verifier_user_id),
        due_text=due_text,
        overdue=overdue,
        late_text=late,
        blocked_text=None
        if a.status != "blocked"
        else f"{a.blocked_reason} · 해결 담당 {a.blocked_resolver}",
        report_text=report,
        history=tuple(_event_text(e, name) for e in events),
        allowed=frozenset(allowed),
        behalf=mode == "behalf",
    )


def _event_text(e: ActionEvent, who: Callable[[int | None], str]) -> str:
    parts = [f"{_when(e.recorded_at)} {EVENT_LABELS[e.kind]} · {who(e.actor_user_id)}"]
    if e.on_behalf:
        parts.append(f"전화 확인 대리 기록({e.counterpart}, {_when(e.contacted_at)} 연락)")
    elif e.kind == "phone_record":
        parts.append(f"{e.counterpart}, {_when(e.contacted_at)} 연락")
    if e.delegated_from_user_id:
        parts.append(f"{who(e.delegated_from_user_id)}의 위임")
    if e.performed_at is not None:
        parts.append(f"실제 처리 {_when(e.performed_at)}")
    if e.reference:
        parts.append(f"참조 {e.reference}")
    if e.body:
        parts.append(e.body)
    return " · ".join(parts)


def _editor(
    members: tuple[SiteMember, ...],
    participants: dict[int, str],
    form: CandidateForm,
    suggestions: tuple[str, ...],
    errors: tuple[str, ...],
) -> CandidateEditor:
    workers = [m for m in members if m.role in ACTION_ROLES]
    return CandidateEditor(
        participants=tuple(
            Option(pid, label, str(pid) == form.performing_participant_id)
            for pid, label in participants.items()
        ),
        assignees=tuple(
            Option(
                m.user_id,
                f"{m.display_name} · {m.organization_name}",
                str(m.user_id) == form.assignee_user_id,
            )
            for m in workers
        ),
        verifiers=tuple(
            Option(
                m.user_id,
                f"{m.display_name} · {m.organization_name}",
                str(m.user_id) == form.verifier_user_id,
            )
            for m in workers
        ),
        form=form,
        title_suggestions=suggestions,
        errors=errors,
    )


def _event(a: ActionItem, kind: str, actor_id: int, now: datetime) -> ActionEvent:
    return ActionEvent(
        action_id=a.id,
        revision_id=a.revision_id,
        kind=kind,
        actor_user_id=actor_id,
        recorded_at=now,
        on_behalf=False,
        body="",
        counterpart="",
        reference="",
    )


def _due(form: CandidateForm) -> tuple[datetime | None, str | None]:
    if not form.due_date.strip() and not form.due_time.strip():
        if not form.due_note.strip():
            return None, "기한을 정하거나, 기한이 미정이면 그 사유를 입력하세요."
        return None, None
    due_at = _local(form.due_date, form.due_time)
    if due_at is None:
        return None, "기한은 날짜와 시각을 함께 입력하세요."
    return due_at, None


def _due_text(a: ActionItem, now: datetime) -> tuple[str, bool]:
    if a.due_at is None:
        return f"기한 미정 · {a.due_note}", False
    overdue = a.due_at < now and a.status in ("requested", "accepted", "blocked")
    return f"{_when(a.due_at)}까지" + (" · 기한 지남" if overdue else ""), overdue


def _local(day: str, at: str) -> datetime | None:
    try:
        return datetime.combine(
            date.fromisoformat(day.strip()), time.fromisoformat(at.strip()), KST
        )
    except ValueError:
        return None


def _when(at: datetime | None) -> str:
    if at is None:
        return "시각 없음"
    local = at.astimezone(KST)
    return f"{local:%m/%d}({_WEEKDAYS[local.weekday()]}) {local:%H:%M}"


def _int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None
