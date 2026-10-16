"""시연용 가상 현장·업체·참여자·작업을 개발 DB에 만든다(D-056 합성 자료, 실제 회사 아님).

원청 1곳과 공종별 협력업체·공급사·감리를 만들고, 오늘부터 일주일 작업을 올린다.
공온 점검이 보이도록 업체 미지정·위치 없음·같은 곳 같은 시간 겹침을 일부러 섞는다.
회사·사람 이름은 모두 지어낸 것이며 이름 앞에 [가상]을 붙인다. 같은 계정이 있으면 만들지 않는다.

    PYTHONUTF8=1 uv run python scripts/seed_demo.py
    PYTHONUTF8=1 uv run python scripts/seed_demo.py --viewer me@example.com  # 내 계정에 열람 권한
"""

import argparse
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
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

PASSWORD = "gongon-demo-1234"
DOMAIN = "demo.gongon.test"  # 실제로 받을 수 없는 시험용 도메인
SITE = SiteForm(
    name="[가상] 한결 리버뷰 아파트 신축공사",
    road_address="서울 중구 세종대로 110",
    latitude="37.5665",
    longitude="126.9780",
)


@dataclass(frozen=True)
class Person:
    key: str  # 이메일 앞부분
    name: str
    company: str
    role: str  # coordinator(원청만) | assignee | viewer
    duty: str  # 표시용 직무


PRIME = "[가상] 한결종합건설"
PEOPLE = (
    Person("pm", "김도윤 소장", PRIME, "coordinator", "현장소장"),
    Person("works", "박서연 과장", PRIME, "coordinator", "공무·공정"),
    Person("safety", "이준호 대리", PRIME, "assignee", "안전관리자"),
    Person("quality", "정하늘 대리", PRIME, "assignee", "품질관리자"),
    Person("frame", "최민석 반장", "[가상] 대성골조", "assignee", "철근콘크리트(골조) 협력업체"),
    Person("steel", "정해원 소장", "[가상] 우진철강", "assignee", "철골 협력업체"),
    Person("pump", "오상훈 기사", "[가상] 서해펌프", "assignee", "콘크리트 펌프카 임대"),
    Person("remicon", "한지민 주임", "[가상] 동부레미콘", "assignee", "레미콘 공급사"),
    Person("crane", "강태호 기사", "[가상] 미래크레인", "assignee", "이동식 크레인·양중"),
    Person("water", "윤가은 실장", "[가상] 청솔방수", "assignee", "방수 협력업체"),
    Person("elec", "조성민 과장", "[가상] 새벽전기", "assignee", "전기 협력업체"),
    Person("scaffold", "임동현 반장", "[가상] 평화가설", "assignee", "비계·가설 협력업체"),
    Person("cm", "문하늘 감리원", "[가상] 정도건설사업관리", "viewer", "감리(건설사업관리)"),
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
            print("이미 시연 자료가 있습니다(pm@demo.gongon.test). 새로 만들지 않았습니다.")
            return 0
        users: dict[str, CurrentUser] = {}
        for p in PEOPLE:
            # 같은 회사 사람은 첫 사람이 만든 회사에 붙여야 하지만 가입 화면은 회사를 새로 만든다.
            # 시연에서는 회사 이름이 같으면 같은 업체로 본다(참여 업체는 회사 단위).
            user_id, errors = auth_service.signup(
                session,
                SignupForm(email=f"{p.key}@{DOMAIN}", display_name=p.name,
                           organization_name=p.company, password=PASSWORD),
            )  # fmt: skip
            if user_id is None:
                print(f"가입 실패 {p.key}: {errors}")
                return 1
            info = auth_service.describe_users(session, [user_id])[user_id]
            users[p.key] = CurrentUser(info.user_id, info.email, info.display_name,
                                       info.organization_id, info.organization_name)  # fmt: skip
        _merge_companies(session, users)
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
        for p in PEOPLE[1:]:
            errors = teams_service.add_member(
                session, site_id, pm, f"{p.key}@{DOMAIN}", p.role, now
            )
            if errors:
                print(f"참여자 추가 실패 {p.key}: {errors}")
                return 1
        if args.viewer:
            errors = teams_service.add_member(session, site_id, pm, args.viewer, "viewer", now)
            print("열람자 추가:", "실패 " + " ".join(errors) if errors else args.viewer)
        labels = teams_service.participant_labels(session, site_id)
        participants = {label.split(" · ")[0]: pid for pid, label in labels.items()}
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


def _merge_companies(session: Session, users: dict[str, CurrentUser]) -> None:
    """가입이 사람마다 회사를 새로 만들므로, 같은 이름의 회사는 첫 회사로 합친다(시연 자료 전용)."""
    session.execute(
        text(
            "UPDATE users u SET organization_id = f.first_id FROM ("
            " SELECT name, min(id) AS first_id FROM organizations GROUP BY name) f, organizations o"
            " WHERE u.organization_id = o.id AND o.name = f.name AND o.id <> f.first_id"
            " AND u.email LIKE :pattern"
        ),
        {"pattern": f"%@{DOMAIN}"},
    )
    session.execute(
        text(
            "DELETE FROM organizations o WHERE o.name LIKE '[가상]%' AND NOT EXISTS"
            " (SELECT 1 FROM users u WHERE u.organization_id = o.id)"
            " AND NOT EXISTS (SELECT 1 FROM project_participants p WHERE p.organization_id = o.id)"
        )
    )
    session.commit()
    for key, user in list(users.items()):
        info = auth_service.describe_users(session, [user.user_id])[user.user_id]
        users[key] = CurrentUser(info.user_id, info.email, info.display_name,
                                 info.organization_id, info.organization_name)  # fmt: skip


def _print_summary(site_id: int, added: int, skipped: int, now: datetime) -> None:
    print(f"[가상] 현장 {site_id} 만듦 · 작업 {added}건 · {now:%m/%d %H:%M}")
    if skipped:
        print(f"  오늘 이미 지난 시각의 작업 {skipped}건은 건너뜀(오늘은 지금 이후 시작만, D-064)")
    print(f"로그인 비밀번호는 모두 {PASSWORD}")
    for p in PEOPLE:
        print(f"  {p.key}@{DOMAIN:<20} {p.name:<8} {p.company} · {p.duty} · {p.role}")


if __name__ == "__main__":
    raise SystemExit(main())
