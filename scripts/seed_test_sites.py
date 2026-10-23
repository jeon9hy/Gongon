# ruff: noqa: E501  (시드 자료 표는 한 줄에 한 업체·현장이 읽기 쉽다)
"""내 계정에 시험용 현장 자료를 채운다(D-056 합성 자료, 실제 회사·현장 아님).

- 내 계정(--owner, 원청 조정자)의 기존 현장은 비어 있는 것만 채운다: 협력업체(맡은 업종 포함),
  협력업체 담당자 계정 연결, 오늘부터 일주일 작업, 변경 건과 후속 조치.
- 새 [TEST] 현장을 만들어 내 현장이 모두 7곳이 되게 한다. 현장 코드는 TEST-0000부터(D-095).
- 변경 제안·확정은 내 회사의 도우미 공무 계정(test-works@demo.gongon.test)이 하고, 완료 보고의
  검증자는 나다. 그래서 내 홈의 내 차례에 검증·막힘·변경 검토가 실제로 쌓인다.
- 조치 상태: 응답 대기, 완료 보고(내가 검증할 차례), 막힘, 변경 검토 중, 일부 현장은 검증 완료.
- 이름이 'asd'인 업체는 '한빛자재'로 바꾼다(개발자 요청).

    PYTHONUTF8=1 uv run python scripts/seed_test_sites.py --owner sim5213@naver.com --reset
"""

import argparse
import re
import secrets
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_engine
from app.features.actions.models import ActionItem
from app.features.auth import service as auth_service
from app.features.auth.models import Organization
from app.features.auth.schemas import CurrentUser, SignupForm
from app.features.changes.models import ChangeCase, ChangeRevision
from app.features.schedules import service as schedules_service
from app.features.schedules.models import WorkItem
from app.features.schedules.schemas import WorkItemForm
from app.features.sites import service as sites_service
from app.features.sites.models import Site
from app.features.sites.schemas import SiteForm
from app.features.teams import repository as teams_repository
from app.features.teams import service as teams_service
from app.features.teams.models import ParticipantContact, ProjectParticipant
from app.features.teams.schemas import ContactForm, ParticipantForm
from app.main import app
from scripts.seed_demo import DOMAIN, PASSWORD

ORIGIN = {"Origin": "http://testserver"}
HELPER = f"test-works@{DOMAIN}"
TARGET_SITES = 7
MARK = "[가상]"  # 이 스크립트가 만든 변경 건의 근거 메모 앞머리(다시 돌려도 겹치지 않게)


@dataclass(frozen=True)
class Company:
    key: str  # 담당자 계정 이메일 test-<key>@...
    name: str
    category: str
    trades: tuple[str, ...]
    note: str
    person: str
    title: str


COMPANIES = (
    Company("frame", "대성골조", "subcontractor", ("철근ㆍ콘크리트공사업",), "지하·지상 골조", "최민석", "반장"),
    Company("steel", "우진철강", "subcontractor", ("철강구조물공사업",), "철골 세우기", "정해원", "소장"),
    Company("water", "청솔방수", "subcontractor", ("도장ㆍ습식ㆍ방수ㆍ석공사업",), "옥상·지하 방수", "윤가은", "실장"),
    Company("crane", "미래크레인", "equipment", ("구조물해체ㆍ비계공사업",), "이동식 크레인", "강태호", "기사"),
    Company("scaffold", "평화가설", "subcontractor", ("구조물해체ㆍ비계공사업",), "비계·가설", "임동현", "반장"),
    Company("elec", "새벽전기", "subcontractor", ("전기·정보통신·소방",), "전기·소방", "조성민", "과장"),
    Company("pump", "서해펌프", "equipment", ("철근ㆍ콘크리트공사업",), "콘크리트 펌프카", "오상훈", "기사"),
)  # fmt: skip
# 기존 현장에 이미 있는 업체의 맡은 업종(이름으로 찾는다)
EXTRA_TRADES = {
    "한길포장": ("지반조성ㆍ포장공사업",),
    "동부레미콘": ("철근ㆍ콘크리트공사업",),
    "정도건설사업관리": ("공사관리(원청·감리)",),
    "한빛자재": ("철근ㆍ콘크리트공사업",),
}

NEW_SITES = (
    ("TEST0000", "[TEST 0000] 리버뷰 아파트 신축공사", "서울 중구 세종대로 110", "37.5665", "126.9780"),
    ("TEST0001", "[TEST 0001] 이천 물류센터 신축공사", "경기 이천시 마장면 서이천로 1", "37.2722", "127.4350"),
    ("TEST0002", "[TEST 0002] 해운대 오피스텔 신축공사", "부산 해운대구 해운대해변로 264", "35.1631", "129.1636"),
    ("TEST0003", "[TEST 0003] 대전 초등학교 증축공사", "대전 서구 둔산로 100", "36.3504", "127.3845"),
    ("TEST0004", "[TEST 0004] 판교 지식산업센터 신축공사", "경기 성남시 분당구 판교역로 166", "37.3947", "127.1112"),
    ("TEST0005", "[TEST 0005] 광주 병원 리모델링공사", "광주 서구 내방로 111", "35.1601", "126.8514"),
    ("TEST0006", "[TEST 0006] 인천 교량 보수공사", "인천 남동구 정각로 29", "37.4563", "126.7052"),
)  # fmt: skip

# (며칠 뒤, 작업, 시작, 끝, 위치, 업체 key). 오늘(0)은 지금 뒤 시작만 들어간다(D-064).
WORK = (
    (0, "도장·방수", "22:00", "23:30", "101동 옥상", "water"),
    (1, "콘크리트 타설", "07:00", "15:00", "101동 3층 슬래브", "frame"),
    (1, "철골 작업", "08:00", "17:00", "102동 지하주차장", "steel"),
    (1, "이동식 크레인", "10:00", "12:00", "102동 지하주차장", "crane"),  # 철골과 같은 곳·같은 시간
    (1, "고소작업대", "13:00", "17:00", "102동 외벽", "scaffold"),
    (2, "도장·방수", "09:00", "16:00", "101동 옥상", "water"),
    (2, "이동식 크레인", "07:30", "11:30", "자재 야적장", "crane"),
    (3, "철골 작업", "08:00", "17:00", "102동 1층 기둥", "steel"),
    (3, "고소작업대", "09:00", "15:00", "101동 전기실", "elec"),
    (4, "콘크리트 타설", "07:00", "13:00", "102동 기초", "pump"),
    (5, "고소작업대", "08:00", "12:00", "101동 외벽 3~5층", "scaffold"),
    (6, "철골 작업", "08:00", "17:00", "102동 2층 보", "steel"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner", required=True, help="자료를 채울 내 계정(원청 조정자) 이메일")
    parser.add_argument(
        "--reset", action="store_true", help="예전 [TEST] 현장을 지우고 새로 만든다"
    )
    args = parser.parse_args()
    now = now_kst()
    with Session(get_engine(), expire_on_commit=False) as session:
        owner = _user(session, args.owner)
        if owner is None:
            print(f"계정을 찾을 수 없습니다: {args.owner}")
            return 1
        if args.reset:
            _reset(session, now)
        _rename_asd(session)
        helper = _helper(session, owner)
        people = {c.key: _sub_account(session, c) for c in COMPANIES}
        mine = [m.site_id for m in teams_service.memberships_of(session, owner.user_id)
                if m.role == "coordinator"]  # fmt: skip
        mine = [s.site_id for s in sites_service.list_sites(session, frozenset(mine))]
        for code, name, road, lat, lng in NEW_SITES:
            if len(mine) >= TARGET_SITES:
                break
            if teams_repository.site_id_for_code(session, code) is not None:
                continue
            mine.append(_new_site(session, owner, code, name, road, lat, lng, now))
        for site_id in mine:
            _fill(session, owner, helper, people, site_id, now)
    for site_id in mine:
        cases = _changes_and_actions(site_id, owner, now)
        print(f"현장 {site_id} 채움 · 변경 {cases}건")
    print(f"내 현장 {len(mine)}곳: {mine}")
    print(f"도우미 공무 계정: {HELPER} / {PASSWORD}")
    print(
        f"협력업체 담당자: test-<업체>@{DOMAIN} / {PASSWORD} (frame·steel·water·crane·scaffold·elec·pump)"
    )
    return 0


def _new_site(session: Session, owner: CurrentUser, code: str, name: str, road: str,
              lat: str, lng: str, now: datetime) -> int:  # fmt: skip
    form = replace(
        SiteForm(name=name, road_address=road, latitude=lat, longitude=lng),
        work_start_date=(now.date() - timedelta(days=60)).isoformat(),
        work_end_date=(now.date() + timedelta(days=420)).isoformat(),
    )
    site_id, errors = sites_service.create_site(session, form, owner, now)
    if site_id is None:
        raise SystemExit(f"현장 생성 실패 {code}: {errors}")
    row = teams_repository.join_code(session, site_id)
    assert row is not None  # 현장을 만들 때 생긴다
    row.code = code
    session.commit()
    print(f"새 현장 {site_id} {name} (코드 {code[:4]}-{code[4:]})")
    return site_id


def _fill(session: Session, owner: CurrentUser, helper: CurrentUser,
          people: dict[str, CurrentUser], site_id: int, now: datetime) -> bool:  # fmt: skip
    """업체·담당자·작업을 채운다. 이 스크립트로 이미 채운 현장(변경 건 있음)이면 건너뛴다."""
    done = session.scalar(
        select(ChangeRevision.id)
        .join(ChangeCase, ChangeCase.id == ChangeRevision.case_id)
        .where(ChangeCase.site_id == site_id, ChangeRevision.basis_note.like(f"{MARK}%"))
    )
    if done is not None:
        return False
    if teams_repository.active_membership(session, helper.user_id, site_id) is None:
        errors = teams_service.add_member(session, site_id, owner, helper.email, "coordinator", now)
        if errors:
            raise SystemExit(f"도우미 추가 실패 {site_id}: {errors}")
    joined = (now.date() - timedelta(days=30)).isoformat()
    ids = _participants(session, site_id)
    for c in COMPANIES:
        if c.name not in ids:
            errors, _ = teams_service.register_participant(
                session, site_id, owner,
                ParticipantForm(c.name, c.category, c.note, "", joined, work_trades=c.trades),
            )  # fmt: skip
            if errors:
                raise SystemExit(f"업체 등록 실패 {c.name}: {errors}")
    ids = _participants(session, site_id)
    trades = {c.name: c.trades for c in COMPANIES} | EXTRA_TRADES
    for name, pid in ids.items():
        p = session.get(ProjectParticipant, pid)
        if p is not None and p.kind != "prime" and not p.work_trades and name in trades:
            p.work_trades = list(trades[name])
    session.commit()
    for c in COMPANIES:
        if teams_repository.active_membership(session, people[c.key].user_id, site_id):
            continue
        contact = session.scalar(select(ParticipantContact.id).where(
            ParticipantContact.site_id == site_id, ParticipantContact.participant_id == ids[c.name],
            ParticipantContact.user_id.is_(None), ParticipantContact.removed_at.is_(None)))  # fmt: skip
        if contact is None:
            teams_service.add_contact(session, site_id, owner, ids[c.name],
                                      ContactForm(c.person, c.title), now)  # fmt: skip
            contact = session.scalar(select(ParticipantContact.id).where(
                ParticipantContact.site_id == site_id,
                ParticipantContact.participant_id == ids[c.name],
                ParticipantContact.name == c.person))  # fmt: skip
        errors = teams_service.add_member(
            session, site_id, owner, people[c.key].email, "assignee", now,
            contact_id=str(contact), same_name=f"attach:{ids[c.name]}",
        )  # fmt: skip
        if errors:
            raise SystemExit(f"담당자 추가 실패 {site_id} {c.key}: {errors}")
    ids = _participants(session, site_id)
    names = {c.key: c.name for c in COMPANIES}
    for offset, work_type, start, end, place, who in WORK:
        day = now.date() + timedelta(days=offset)
        if offset == 0 and start <= f"{now:%H:%M}":
            continue
        first, errors = schedules_service.add_item(
            session, owner, site_id,
            WorkItemForm(work_types=(work_type,), work_dates=(day.isoformat(),), start=start,
                         end=end, location=place,
                         performing_participant_id=str(ids[names[who]])),
            now,
        )  # fmt: skip
        if first is None:
            print(f"  작업 건너뜀 {site_id} {day} {work_type}: {' '.join(errors)}")
    return True


def _changes_and_actions(site_id: int, owner: CurrentUser, now: datetime) -> int:
    """변경 건과 후속 조치를 화면에서 하듯 만든다. 제안·확정은 도우미, 검증자는 나."""
    helper_client = _login(HELPER)
    subs = {c.key: _login(f"test-{c.key}@{DOMAIN}") for c in COMPANIES}
    with Session(get_engine(), expire_on_commit=False) as session:
        ids = _participants(session, site_id)
        users = {c.key: _user(session, f"test-{c.key}@{DOMAIN}") for c in COMPANIES}
        helper = _user(session, HELPER)
        assert helper is not None
        items = list(session.scalars(select(WorkItem).where(
            WorkItem.site_id == site_id, WorkItem.deleted_at.is_(None),
            WorkItem.work_date > now.date())))  # fmt: skip
    names = {c.key: c.name for c in COMPANIES}
    today = now.date()
    report_time = f"{max(now.hour - 1, 0):02d}:00"

    def pick(work_type: str, offset: int, title: str) -> WorkItem | None:
        if title in existing:
            return None  # 이미 만든 장면
        day = today + timedelta(days=offset)
        return next((i for i in items if i.work_type == work_type and i.work_date == day), None)

    with Session(get_engine()) as s:
        existing = set(s.scalars(select(ChangeCase.title).where(ChangeCase.site_id == site_id)))

    def change(it: WorkItem, title: str, reason: str, note: str, shift: int,
               start: str = "", end: str = "") -> tuple[int, int]:  # fmt: skip
        after = it.work_date + timedelta(days=shift)
        r = helper_client.post("/changes", data={
            "site_id": site_id, "work_item_id": it.id, "title": title,
            "after_work_date": after.isoformat(),
            "after_start": start or f"{it.start_local:%H:%M}",
            "after_end": end or f"{it.end_local:%H:%M}", "after_location": it.location,
            "reasons": [reason], "basis_note": f"{MARK} {note}", "plan_version": it.plan_version,
            "submit": "review",
        }, follow_redirects=False)  # fmt: skip
        if r.status_code != 303:
            raise SystemExit(f"변경 제안 실패 {title}: {r.status_code} {_errors(r.text)}")
        case_id = int(re.search(r"/changes/(\d+)", r.headers["location"]).group(1))  # type: ignore[union-attr]
        with Session(get_engine()) as s:
            rev = s.scalars(select(ChangeRevision).where(ChangeRevision.case_id == case_id)
                            .order_by(ChangeRevision.number.desc())).first()  # fmt: skip
            assert rev is not None
            return case_id, rev.id

    def with_action(it: WorkItem, title: str, reason: str, note: str, who: str, action: str,
                    criteria: str, verifier: int) -> tuple[int, int]:  # fmt: skip
        case_id, rev_id = change(it, title, reason, note, 1)
        user = users[who]
        assert user is not None
        r = helper_client.post(f"/changes/{case_id}/revisions/{rev_id}/actions", data={
            "site_id": site_id, "title": action, "required": "1",
            "due_date": (today + timedelta(days=2)).isoformat(), "due_time": "17:00",
            "performing_participant_id": ids[names[who]], "assignee": f"user:{user.user_id}",
            "verifier_user_id": verifier, "done_criteria": criteria,
        }, follow_redirects=False)  # fmt: skip
        if r.status_code != 303:
            raise SystemExit(f"조치 후보 실패 {action}: {r.status_code} {_errors(r.text)}")
        r = helper_client.post(f"/changes/{case_id}/revisions/{rev_id}/confirm",
                               data={"site_id": site_id, "confirm_key": f"seed{rev_id}"},
                               follow_redirects=False)  # fmt: skip
        if r.status_code != 303:
            raise SystemExit(f"확정 실패 {title}: {r.status_code} {_errors(r.text)}")
        with Session(get_engine()) as s:
            a = s.scalars(select(ActionItem).where(ActionItem.case_id == case_id)).one()
            return case_id, a.id

    def act(client: TestClient, case_id: int, action_id: int, kind: str, **form: Any) -> None:
        with Session(get_engine()) as s:
            a = s.get(ActionItem, action_id)
            assert a is not None
            rev = a.revision_id
        r = client.post(f"/changes/{case_id}/actions/{action_id}/{kind}",
                        data={"site_id": site_id, "revision_id": rev, **form},
                        follow_redirects=False)  # fmt: skip
        if r.status_code != 303:
            raise SystemExit(f"조치 {kind} 실패: {r.status_code} {_errors(r.text)}")

    count = 0
    it = pick("철골 작업", 3, "철골 자재 반입 지연으로 하루 연기")
    if it:  # 응답 대기: 우진철강이 아직 답하지 않았다
        with_action(it, "철골 자재 반입 지연으로 하루 연기", "material", "볼트 반입 하루 지연",
                    "steel", "철골 자재 반입 일정 다시 확인", "반입 확정 시각을 받음",
                    owner.user_id)  # fmt: skip
        count += 1
    it = pick("이동식 크레인", 2, "크레인 동선 겹침 조정")
    if it:  # 검증 대기: 미래크레인이 끝냈다고 보고, 검증자는 나
        case_id, action_id = with_action(
            it, "크레인 동선 겹침 조정", "area", "야적장 진입로 겹침", "crane",
            "크레인 위치 변경 계획 제출", "변경 위치 도면을 올림", owner.user_id)  # fmt: skip
        act(subs["crane"], case_id, action_id, "accept")
        act(subs["crane"], case_id, action_id, "report", body="야적장 동쪽으로 위치 변경, 계획서 첨부",
            performed_date=today.isoformat(), performed_time=report_time)  # fmt: skip
        count += 1
    it = pick("도장·방수", 2, "옥상 방수 보수 범위 추가")
    if it:  # 막힘: 청솔방수가 진행할 수 없다고 했다
        case_id, action_id = with_action(
            it, "옥상 방수 보수 범위 추가", "quality", "배수구 주변 들뜸", "water",
            "옥상 배수구 주변 재시공", "재시공 부위 사진과 담수 시험 결과", owner.user_id)  # fmt: skip
        act(subs["water"], case_id, action_id, "accept")
        act(subs["water"], case_id, action_id, "block", body="바탕면이 젖어 시공 불가, 건조 뒤 가능",
            resolver="원청 공무")  # fmt: skip
        count += 1
    it = pick("콘크리트 타설", 4, "타설 시간 두 시간 앞당기기")
    if it:  # 변경 검토: 제안만 하고 아직 확정하지 않았다
        change(it, "타설 시간 두 시간 앞당기기", "schedule", "레미콘 배차 시간 변경", 0,
               start="05:00", end="11:00")  # fmt: skip
        count += 1
    it = pick("고소작업대", 5, "외벽 비계 보강 추가")
    if it and site_id % 2 == 0:  # 검증까지 끝난 건(도우미가 검증)
        case_id, action_id = with_action(
            it, "외벽 비계 보강 추가", "safety", "순회 점검 지적", "scaffold",
            "외벽 비계 연결재 보강", "보강 부위 사진", helper.user_id)  # fmt: skip
        act(subs["scaffold"], case_id, action_id, "accept")
        act(subs["scaffold"], case_id, action_id, "report", body="연결재 12개소 보강",
            performed_date=today.isoformat(), performed_time=report_time)  # fmt: skip
        act(helper_client, case_id, action_id, "verify")
        count += 1
    return count


def _errors(html: str) -> str:
    found = re.findall(r'<div class="alert alert--error"[^>]*>(.*?)</div>', html, re.S)
    return re.sub(r"<[^>]+>", " ", found[0]).strip()[:300] if found else html[:200]


def _login(email: str) -> TestClient:
    client = TestClient(app, headers=ORIGIN)
    r = client.post("/login", data={"email": email, "password": PASSWORD}, follow_redirects=False)
    if r.status_code != 303:
        raise SystemExit(f"로그인 실패 {email}: {r.status_code}")
    return client


def _participants(session: Session, site_id: int) -> dict[str, int]:
    session.expire_all()
    labels = teams_service.participant_labels(session, site_id)
    return {label.split(" · ")[0]: pid for pid, label in labels.items()}


def _user(session: Session, email: str) -> CurrentUser | None:
    info = auth_service.find_user_by_email(session, email)
    if info is None:
        return None
    return CurrentUser(info.user_id, info.email, info.display_name,
                       info.organization_id, info.organization_name)  # fmt: skip


def _signup(session: Session, email: str, name: str, company: str, phone: str) -> CurrentUser:
    found = _user(session, email)
    if found is not None:
        return found
    user_id, errors = auth_service.signup(
        session, SignupForm(email=email, display_name=name, organization_name=company,
                            password=PASSWORD, phone=phone))  # fmt: skip
    if user_id is None:
        raise SystemExit(f"가입 실패 {email}: {errors}")
    made = _user(session, email)
    assert made is not None
    return made


def _helper(session: Session, owner: CurrentUser) -> CurrentUser:
    """내 회사(원청) 소속 도우미 공무 계정. 조정자는 원청 소속만 될 수 있다(D-057)."""
    helper = _signup(session, HELPER, "박서연 과장", owner.organization_name, "01000008999")
    if helper.organization_id != owner.organization_id:
        auth_service.move_user_to_organization(session, helper.user_id, owner.organization_id)
        session.commit()
        moved = _user(session, HELPER)
        assert moved is not None
        helper = moved
    return helper


def _sub_account(session: Session, c: Company) -> CurrentUser:
    index = [x.key for x in COMPANIES].index(c.key)
    return _signup(session, f"test-{c.key}@{DOMAIN}", f"{c.person} {c.title}", c.name,
                   f"0100000{9000 + index:04d}")  # fmt: skip


def _rename_asd(session: Session) -> None:
    for org in session.scalars(select(Organization).where(Organization.name == "asd")):
        org.name = "한빛자재"
        print(f"업체 이름 바꿈: asd → 한빛자재 (회사 {org.id})")
    session.commit()


def _reset(session: Session, now: datetime) -> None:
    """예전 [TEST] 현장(누가 만들었든)을 지우고 그 코드를 아무 값으로 바꿔 TEST 코드를 비운다."""
    for site in session.scalars(select(Site).where(Site.name.like("[TEST %"),
                                                   Site.deleted_at.is_(None))):  # fmt: skip
        site.deleted_at = now
        print(f"지움: 현장 {site.id} {site.name}")
    for code in [f"TEST000{i}" for i in range(len(NEW_SITES))]:
        site_id = teams_repository.site_id_for_code(session, code)
        row = None if site_id is None else teams_repository.join_code(session, site_id)
        if row is not None:
            row.code = "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(8))
    session.commit()


if __name__ == "__main__":
    raise SystemExit(main())
