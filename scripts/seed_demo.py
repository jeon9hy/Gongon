"""시연용 가상 현장·업체·참여자·작업을 개발 DB에 만든다(D-056 합성 자료, 실제 회사 아님).

원청 1곳과 공종별 협력업체·공급사·감리를 만들고, 오늘부터 일주일 작업을 올린다.
업체는 명부로 먼저 등록하고(D-066) 사람은 담당자 명부와 로그인 계정을 연결한다.
공온 점검이 보이도록 업체 미지정·위치 없음·같은 곳 같은 시간 겹침을 일부러 섞는다.
회사·사람 이름은 모두 지어낸 것이며 이름 앞에 을 붙인다. 같은 계정이 있으면 만들지 않는다.

    PYTHONUTF8=1 uv run python scripts/seed_demo.py
    PYTHONUTF8=1 uv run python scripts/seed_demo.py --viewer me@example.com  # 내 계정에 열람 권한
"""

import argparse
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_engine
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser, SignupForm
from app.features.schedules import service as schedules_service
from app.features.schedules.schemas import WorkItemForm
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteForm
from app.features.teams import service as teams_service
from app.features.teams.models import ParticipantContact
from app.features.teams.schemas import ContactForm, ParticipantForm

PASSWORD = "gongon-demo-1234"
DOMAIN = "demo.gongon.test"  # 실제로 받을 수 없는 시험용 도메인
SITE = SiteForm(
    name="한결 리버뷰 아파트 신축공사",
    road_address="서울 중구 세종대로 110",
    latitude="37.5665",
    longitude="126.9780",
)


def demo_phone(index: int) -> str:
    """시연 계정의 가상 번호 010-0000-0001부터(실제 번호가 아님, D-073)."""
    return f"0100000{index + 1:04d}"


def _fill_demo_phones(session: Session) -> int:
    """C04-13 전에 만든 시연 계정에 가상 번호를 넣는다. 번호가 있으면 그대로 둔다."""
    added = 0
    for index, p in enumerate(PEOPLE):
        info = auth_service.find_user_by_email(session, f"{p.key}@{DOMAIN}")
        if info is None or info.phone:
            continue
        if not auth_service.set_phone(session, info.user_id, demo_phone(index)):
            added += 1
    return added


@dataclass(frozen=True)
class Person:
    key: str  # 이메일 앞부분
    name: str
    company: str
    role: str  # coordinator(원청만) | assignee | viewer
    duty: str  # 표시용 직무


PRIME = "한결종합건설"
# 업체 → (구분, 맡은 공종). 원청은 명부 등록 대상이 아니다(현장을 만들 때 생김).
COMPANIES = {
    "대성골조": ("subcontractor", "철근콘크리트(골조)"),
    "우진철강": ("subcontractor", "철골"),
    "서해펌프": ("equipment", "콘크리트 펌프카"),
    "동부레미콘": ("supplier", "레미콘"),
    "미래크레인": ("equipment", "이동식 크레인·양중"),
    "청솔방수": ("subcontractor", "방수"),
    "새벽전기": ("subcontractor", "전기"),
    "평화가설": ("subcontractor", "비계·가설"),
    "정도건설사업관리": ("supervision", "건설사업관리"),
}
# 계정 없는 명부 담당자(전화 대리 기록 대상, C06). 번호는 실제로 걸리지 않는 형식이다.
EXTRA_CONTACTS = (
    ("동부레미콘", "배차 담당", "출하 배차", "010-0000-0001"),
    ("서해펌프", "현장 배정", "공무", "010-0000-0002"),
)
PEOPLE = (
    Person("pm", "김도윤 소장", PRIME, "coordinator", "현장소장"),
    Person("works", "박서연 과장", PRIME, "coordinator", "공무·공정"),
    Person("safety", "이준호 대리", PRIME, "assignee", "안전관리자"),
    Person("quality", "정하늘 대리", PRIME, "assignee", "품질관리자"),
    Person("frame", "최민석 반장", "대성골조", "assignee", "철근콘크리트(골조) 협력업체"),
    Person("steel", "정해원 소장", "우진철강", "assignee", "철골 협력업체"),
    Person("pump", "오상훈 기사", "서해펌프", "assignee", "콘크리트 펌프카 임대"),
    Person("remicon", "한지민 주임", "동부레미콘", "assignee", "레미콘 공급사"),
    Person("crane", "강태호 기사", "미래크레인", "assignee", "이동식 크레인·양중"),
    Person("water", "윤가은 실장", "청솔방수", "assignee", "방수 협력업체"),
    Person("elec", "조성민 과장", "새벽전기", "assignee", "전기 협력업체"),
    Person("scaffold", "임동현 반장", "평화가설", "assignee", "비계·가설 협력업체"),
    Person("cm", "문하늘 감리원", "정도건설사업관리", "viewer", "감리(건설사업관리)"),
)

# (며칠 뒤, 공종, 시작, 끝, 위치, 실행 업체 키 또는 None)
# 오늘(0일)은 지금 뒤에 시작하는 작업만 올라간다(D-064). 시각이 지났으면 건너뛴다.
WORK = (
    (0, "도장·방수", "17:00", "19:00", "101동 옥상", "water"),
    (0, "고소작업대", "17:30", "19:30", "", None),
    (1, "콘크리트 타설", "07:00", "15:00", "101동 3층 슬래브", "frame"),
    (1, "철골 작업", "08:00", "17:00", "102동 지하주차장", "steel"),
    (1, "이동식 크레인", "10:00", "12:00", "102동 지하주차장", "crane"),  # 철골과 같은 곳·같은 시간
    (1, "고소작업대", "13:00", "17:00", "102동 외벽", None),  # 업체 미지정
    (2, "도장·방수", "09:00", "16:00", "101동 옥상", "water"),
    (2, "이동식 크레인", "07:30", "11:30", "자재 야적장", "crane"),
    (3, "철골 작업", "08:00", "17:00", "102동 1층 기둥", "steel"),
    (3, "고소작업대", "09:00", "15:00", "", "elec"),  # 위치 없음
    (4, "콘크리트 타설", "07:00", "13:00", "102동 기초", "frame"),
    (5, "고소작업대", "08:00", "12:00", "101동 외벽 3~5층", "scaffold"),
    (6, "철골 작업", "08:00", "17:00", "102동 2층 보", "steel"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--viewer", help="이 이메일 계정을 현장 열람자로 넣는다(먼저 가입해 둔다)")
    args = parser.parse_args()
    now = now_kst()
    with Session(get_engine(), expire_on_commit=False) as session:
        if auth_service.find_user_by_email(session, f"pm@{DOMAIN}") is not None:
            added = _fill_demo_phones(session)
            print("이미 시연 자료가 있습니다(pm@demo.gongon.test). 새로 만들지 않았습니다.")
            if added:
                print(f"번호 없는 시연 계정 {added}명에 가상 번호를 넣었습니다.")
            return 0
        users: dict[str, CurrentUser] = {}
        for index, p in enumerate(PEOPLE):
            # 가입은 사람마다 회사를 새로 만든다. 현장에 붙일 때 같은 이름 업체에 붙인다(D-066).
            user_id, errors = auth_service.signup(
                session,
                SignupForm(email=f"{p.key}@{DOMAIN}", display_name=p.name,
                           organization_name=p.company, password=PASSWORD,
                           phone=demo_phone(index)),
            )  # fmt: skip
            if user_id is None:
                print(f"가입 실패 {p.key}: {errors}")
                return 1
            info = auth_service.describe_users(session, [user_id])[user_id]
            users[p.key] = CurrentUser(info.user_id, info.email, info.display_name,
                                       info.organization_id, info.organization_name)  # fmt: skip
        pm = users["pm"]
        site_id, errors = sites_service.create_site(
            session,
            replace(
                SITE,
                work_start_date=(now.date() - timedelta(days=60)).isoformat(),
                work_end_date=(now.date() + timedelta(days=420)).isoformat(),
            ),
            pm,
            now,
        )  # fmt: skip
        if site_id is None:
            print(f"현장 생성 실패: {errors}")
            return 1
        joined = (now.date() - timedelta(days=30)).isoformat()
        for company, (category, trade) in COMPANIES.items():
            errors, _ = teams_service.register_participant(
                session, site_id, pm, ParticipantForm(company, category, trade, "", joined)
            )
            if errors:
                print(f"업체 등록 실패 {company}: {errors}")
                return 1
        ids = _participant_ids(session, site_id)
        for p in PEOPLE:
            teams_service.add_contact(session, site_id, pm, ids[p.company],
                                      ContactForm(p.name.split()[0], p.duty[:40]), now)  # fmt: skip
        for company, name, title, phone in EXTRA_CONTACTS:
            teams_service.add_contact(session, site_id, pm, ids[company],
                                      ContactForm(name, title, phone), now)  # fmt: skip
        for p in PEOPLE[1:]:
            contact = session.scalar(
                select(ParticipantContact.id).where(
                    ParticipantContact.site_id == site_id,
                    ParticipantContact.participant_id == ids[p.company],
                    ParticipantContact.name == p.name.split()[0],
                )
            )
            errors = teams_service.add_member(
                session, site_id, pm, f"{p.key}@{DOMAIN}", p.role, now,
                contact_id=str(contact), same_name=f"attach:{ids[p.company]}",
            )  # fmt: skip
            if errors:
                print(f"참여자 추가 실패 {p.key}: {errors}")
                return 1
        if args.viewer:
            errors = teams_service.add_member(session, site_id, pm, args.viewer, "viewer", now,
                                              same_name="separate")  # fmt: skip
            print("열람자 추가:", "실패 " + " ".join(errors) if errors else args.viewer)
        participants = _participant_ids(session, site_id)
        companies = {p.key: p.company for p in PEOPLE}
        added = skipped = 0
        for offset, work_type, start, end, place, performer in WORK:
            day: date = now.date() + timedelta(days=offset)
            if offset == 0 and start <= f"{now:%H:%M}":
                skipped += 1
                continue
            first, errors = schedules_service.add_item(
                session, pm, site_id,
                WorkItemForm(work_types=(work_type,), work_dates=(day.isoformat(),), start=start,
                             end=end, location=place,
                             performing_participant_id="" if performer is None
                             else str(participants[companies[performer]])),
                now,
            )  # fmt: skip
            if first is None:
                print(f"작업 실패 {day} {work_type}: {errors}")
                return 1
            added += 1
        session.commit()
    _print_summary(site_id, added, skipped, now)
    return 0


def _participant_ids(session: Session, site_id: int) -> dict[str, int]:
    """회사 이름 → 참여 업체 ID(시연 자료는 이름이 겹치지 않는다)."""
    labels = teams_service.participant_labels(session, site_id)
    return {label.split(" · ")[0]: pid for pid, label in labels.items()}


def _print_summary(site_id: int, added: int, skipped: int, now: datetime) -> None:
    print(f"현장 {site_id} 만듦 · 작업 {added}건 · {now:%m/%d %H:%M}")
    if skipped:
        print(f"  오늘 이미 지난 시각의 작업 {skipped}건은 건너뜀(오늘은 지금 이후 시작만, D-064)")
    print(f"로그인 비밀번호는 모두 {PASSWORD}")
    for p in PEOPLE:
        print(f"  {p.key}@{DOMAIN:<20} {p.name:<8} {p.company} · {p.duty} · {p.role}")


if __name__ == "__main__":
    raise SystemExit(main())
