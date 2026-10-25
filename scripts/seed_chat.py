# ruff: noqa: E501  (대화 문장은 한 줄로 두는 편이 읽기 쉽다)
"""현장 대화방에 그 현장의 실제 자료로 만든 예시 대화를 넣는다(D-056 합성 자료, 개발 DB 전용).

대화 내용은 지어내지 않고 그 현장에 등록된 것에서 만든다: 오늘·내일 작업(시간·위치·실행 업체),
열린 변경 건(대화에 카드로 붙인다), 보류·완료 보고된 조치, 내일 날씨 판정. 말하는 사람은 그 현장의
활성 참여자다(원청 조정자, 해당 협력업체 담당자). 시각은 지금부터 몇 시간 전으로 둔다.

- 참여자가 둘 이상인 현장만 채운다(혼자 있는 시험 현장은 대화 상대가 없다).
- 이미 대화가 3건 이상인 방은 건너뛴다. --reset이면 그 현장들의 대화를 지우고 다시 넣는다.

    PYTHONUTF8=1 uv run python scripts/seed_chat.py
    PYTHONUTF8=1 uv run python scripts/seed_chat.py --site 39 --site 45 --reset
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_engine
from app.features.actions.models import ActionItem
from app.features.auth.models import Organization, User
from app.features.changes.models import ChangeCase, ChangeRevision
from app.features.chat.models import SiteMessage
from app.features.judgments.models import Judgment
from app.features.schedules.models import WorkItem
from app.features.sites.models import Site
from app.features.teams.models import ProjectMembership, ProjectParticipant

KEEP_IF_AT_LEAST = 3
# 협력업체 대답. 같은 방에서 같은 문장이 되풀이되지 않게 돌아가며 쓴다
REPLIES = (
    "확인했습니다. 저희 쪽 인원·장비 일정 맞춰 보고 조치에 답 남길게요.",
    "네 봤습니다. 바뀐 시간으로 반장님께 전달하고 조치 수락해 둘게요.",
)


@dataclass(frozen=True)
class Member:
    user_id: int
    name: str
    participant_id: int
    prime: bool
    coordinator: bool


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--site", type=int, action="append", help="채울 현장 id(여러 번 쓸 수 있다)"
    )
    parser.add_argument(
        "--reset", action="store_true", help="그 현장들의 대화를 지우고 다시 넣는다"
    )
    args = parser.parse_args()
    now = now_kst()
    with Session(get_engine(), expire_on_commit=False) as session:
        for site in _target_sites(session, args.site):
            print(f"{site.name}(#{site.id}): {_fill(session, site, now, args.reset)}")
        session.commit()
    return 0


def _target_sites(session: Session, only: list[int] | None) -> list[Site]:
    active = (
        select(ProjectMembership.site_id)
        .where(ProjectMembership.revoked_at.is_(None))
        .group_by(ProjectMembership.site_id)
        .having(func.count() >= 2)
    )
    query = select(Site).where(Site.id.in_(active)).order_by(Site.id)
    if only:
        query = query.where(Site.id.in_(only))
    return list(session.scalars(query))


def _members(session: Session, site_id: int) -> list[Member]:
    rows = session.execute(
        select(ProjectMembership, ProjectParticipant, User)
        .join(ProjectParticipant, ProjectParticipant.id == ProjectMembership.participant_id)
        .join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.site_id == site_id, ProjectMembership.revoked_at.is_(None))
        .where(ProjectMembership.role.in_(("coordinator", "assignee")))
        .order_by(ProjectMembership.id)
    ).all()
    return [
        Member(u.id, u.display_name, p.id, p.kind == "prime", m.role == "coordinator")
        for m, p, u in rows
    ]


def _company_names(session: Session, site_id: int) -> dict[int, str]:
    rows = session.execute(
        select(ProjectParticipant.id, Organization.name)
        .join(Organization, Organization.id == ProjectParticipant.organization_id)
        .where(ProjectParticipant.site_id == site_id)
    )
    return dict(rows.all())


def _fill(session: Session, site: Site, now: datetime, reset: bool) -> str:
    existing = session.scalar(
        select(func.count()).select_from(SiteMessage).where(SiteMessage.site_id == site.id)
    )
    if existing and not reset and existing >= KEEP_IF_AT_LEAST:
        return f"이미 대화 {existing}건, 건너뜀"
    if reset:
        session.execute(delete(SiteMessage).where(SiteMessage.site_id == site.id))
    members = _members(session, site.id)
    coord = next((m for m in members if m.coordinator), None)
    if coord is None:
        return "원청 조정자가 없어 건너뜀"
    by_company: dict[int, Member] = {}
    for m in members:
        if not m.prime:
            by_company.setdefault(m.participant_id, m)
    names = _company_names(session, site.id)
    today = now.date()
    lines: list[tuple[Member, str, int | None]] = []
    # 묶음마다 하루 중 그럴듯한 시각에서 시작한다: (몇 번째 줄부터, 시각)
    marks: list[tuple[int, time]] = []

    def worker(participant_id: int | None) -> Member | None:
        return by_company.get(participant_id) if participant_id is not None else None

    # 1) 오늘 작업 공지와 첫 업체의 대답(작업 시작 전)
    marks.append((len(lines), time(6, 50)))
    todays = _items(session, site.id, today)
    if todays:
        first = todays[0]
        lines.append(
            (
                coord,
                f"오늘 작업 {len(todays)}건이에요. 첫 작업은 {_hm(first)} {first.work_type}{_at(first)}입니다.",
                None,
            )
        )
        for it in todays[:3]:
            w = worker(it.performing_participant_id)
            if w is not None:
                lines.append(
                    (
                        w,
                        f"{names.get(w.participant_id, '저희')} {it.work_type} 인원 들어왔습니다.{_place_reply(it)}",
                        None,
                    )
                )
                break

    marks.append((len(lines), time(10, 20)))
    # 2) 열린 변경 건: 원청이 카드로 올리고, 그 작업의 실행 업체가 답한다.
    #    문구는 최신 버전 상태를 따른다(검토 중이면 '올렸어요', 확정이면 '확정했어요').
    for n, (case, item, status) in enumerate(_open_cases(session, site.id)[:2]):
        what = f"{item.work_type}{_at(item)}"
        if status == "confirmed":
            text = f"'{case.title}' 확정했어요. {what} 일정이 바뀌었으니 맡은 후속 조치 확인 부탁드려요."
        else:
            text = (
                f"'{case.title}' 변경 올렸어요. {what} 관련이라 해당 업체는 영향 있는지 봐 주세요."
            )
        lines.append((coord, text, case.id))
        w = worker(item.performing_participant_id)
        if w is not None:
            lines.append((w, REPLIES[n % len(REPLIES)], None))

    # 3) 보류·완료 보고된 조치(오후)
    marks.append((len(lines), time(13, 30)))
    for action in _actions(session, site.id, "blocked")[:1]:
        w = worker(action.performing_participant_id)
        if w is not None:
            reason = (action.blocked_reason or "").strip() or "사유는 조치에 적어 뒀어요"
            lines.append((w, f"'{action.title}'은 보류했어요. {reason}", None))
            resolver = (action.blocked_resolver or "").strip()
            lines.append(
                (
                    coord,
                    f"알겠습니다. {'' if not resolver or '원청' in resolver else resolver + '와 '}오늘 안에 확인해서 다시 알려 드릴게요.",
                    None,
                )
            )
    for action in _actions(session, site.id, "reported")[:1]:
        w = worker(action.performing_participant_id)
        if w is not None:
            lines.append((w, f"'{action.title}' 완료 보고 올렸습니다. 확인 부탁드려요.", None))
            lines.append((coord, "네, 올려 주신 근거 보고 확인할게요.", None))

    # 4) 내일 작업과 날씨 판정(퇴근 전)
    marks.append((len(lines), time(17, 0)))
    tomorrow = today + timedelta(days=1)
    tomorrows = _items(session, site.id, tomorrow)
    if tomorrows:
        nxt = tomorrows[0]
        w = worker(nxt.performing_participant_id)
        company = names.get(nxt.performing_participant_id or -1, "")
        lines.append(
            (
                coord,
                f"내일 첫 작업은 {_hm(nxt)} {nxt.work_type}{_at(nxt)}입니다.{f' {company} 준비 부탁드려요.' if company else ''}",
                None,
            )
        )
        if w is not None:
            lines.append((w, "네, 시간 맞춰 준비하겠습니다.", None))
        for work_type, verdict in _weather(session, site.id, tomorrow)[:1]:
            lines.append(
                (
                    coord,
                    f"내일 {work_type}은 공온 판정이 '{verdict}'이에요. 아침에 예보 다시 보고 진행 여부 정할게요.",
                    None,
                )
            )

    if not lines:
        return "넣을 자료가 없음"
    # 시각: 묶음 시작 시각부터 9분씩. 아직 오지 않은 시각의 말은 넣지 않는다.
    added = 0
    for n, (who, body, case_id) in enumerate(lines):
        start_line, clock = max((m for m in marks if m[0] <= n), key=lambda m: m[0])
        at = datetime.combine(today, clock, tzinfo=now.tzinfo) + timedelta(
            minutes=9 * (n - start_line)
        )
        if at > now:
            continue
        session.add(
            SiteMessage(
                site_id=site.id,
                author_user_id=who.user_id,
                body=body[:500],
                linked_case_id=case_id,
                created_at=at,
            )
        )
        added += 1
    return f"대화 {added}건 넣음"


def _items(session: Session, site_id: int, day: date) -> list[WorkItem]:
    return list(
        session.scalars(
            select(WorkItem)
            .where(
                WorkItem.site_id == site_id,
                WorkItem.work_date == day,
                WorkItem.deleted_at.is_(None),
            )
            .order_by(WorkItem.start_local, WorkItem.id)
        )
    )


def _open_cases(session: Session, site_id: int) -> list[tuple[ChangeCase, WorkItem, str]]:
    """닫히지 않은 변경 건, 그 작업, 최신 버전 상태(최근 순)."""
    latest = (
        select(ChangeRevision.case_id, func.max(ChangeRevision.number).label("number"))
        .group_by(ChangeRevision.case_id)
        .subquery()
    )
    rows = session.execute(
        select(ChangeCase, WorkItem, ChangeRevision.status)
        .join(WorkItem, WorkItem.id == ChangeCase.work_item_id)
        .join(latest, latest.c.case_id == ChangeCase.id)
        .join(
            ChangeRevision,
            (ChangeRevision.case_id == ChangeCase.id) & (ChangeRevision.number == latest.c.number),
        )
        .where(ChangeCase.site_id == site_id, ChangeCase.closed_at.is_(None))
        .order_by(ChangeCase.created_at.desc())
    )
    return [(c, w, status) for c, w, status in rows.all()]


def _actions(session: Session, site_id: int, status: str) -> list[ActionItem]:
    return list(
        session.scalars(
            select(ActionItem)
            .where(
                ActionItem.site_id == site_id,
                ActionItem.status == status,
                ActionItem.replaced_by_id.is_(None),
            )
            .order_by(ActionItem.id)
        )
    )


def _weather(session: Session, site_id: int, day: date) -> list[tuple[str, str]]:
    rows = session.execute(
        select(Judgment.work_type, Judgment.verdict)
        .where(Judgment.site_id == site_id, Judgment.target_date == day)
        .where(Judgment.verdict.in_(("중지 검토", "확인 필요")))
        .order_by(Judgment.judged_at.desc())
    )
    seen: dict[str, str] = {}
    for work_type, verdict in rows.all():
        seen.setdefault(work_type, verdict)
    return list(seen.items())


def _hm(item: WorkItem) -> str:
    return item.start_local.strftime("%H:%M")


def _at(item: WorkItem) -> str:
    return f"({item.location})" if item.location else ""


def _place_reply(item: WorkItem) -> str:
    return (
        f" {item.location} {_hm(item)}부터 바로 시작할게요."
        if item.location
        else f" {_hm(item)}부터 시작할게요."
    )


if __name__ == "__main__":
    raise SystemExit(main())
