"""코드로 참여를 시험할 가상 현장 3곳을 개발 DB에 만든다(D-056 합성 자료, 실제 회사·현장 아님).

현장마다 원청·협력업체·담당자 명부와 오늘부터 일주일 작업을 넣고, 현장 코드를 외우기 쉬운
TEST-0000, TEST-0001, TEST-0002로 둔다(만들어지는 코드와 달리 0·1이 들어가도 입력은 받는다, D-095).
현장 주인은 시험용 조정자 계정 하나다. 내 계정으로 로그인해 코드로 참여에 코드를 넣으면
담당자로 들어간다.
이미 같은 코드가 있으면 그 현장은 건너뛴다.

    PYTHONUTF8=1 uv run python scripts/seed_test_sites.py
"""

import sys
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_engine
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser, SignupForm
from app.features.schedules import service as schedules_service
from app.features.schedules.schemas import WorkItemForm
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteForm
from app.features.teams import repository as teams_repository
from app.features.teams import service as teams_service
from app.features.teams.schemas import ContactForm, ParticipantForm
from scripts.seed_demo import COMPANIES, DOMAIN, PASSWORD, PEOPLE, WORK

OWNER_EMAIL = f"testowner@{DOMAIN}"


@dataclass(frozen=True)
class TestSite:
    code: str  # 하이픈 없이 저장
    form: SiteForm


SITES = (
    TestSite("TEST0000", SiteForm(name="[TEST 0000] 리버뷰 아파트 신축공사",
                                  road_address="서울 중구 세종대로 110",
                                  latitude="37.5665", longitude="126.9780")),
    TestSite("TEST0001", SiteForm(name="[TEST 0001] 이천 물류센터 신축공사",
                                  road_address="경기 이천시 마장면 서이천로 1",
                                  latitude="37.2722", longitude="127.4350")),
    TestSite("TEST0002", SiteForm(name="[TEST 0002] 해운대 오피스텔 신축공사",
                                  road_address="부산 해운대구 해운대해변로 264",
                                  latitude="35.1631", longitude="129.1636")),
)  # fmt: skip


def main() -> int:
    now = now_kst()
    with Session(get_engine(), expire_on_commit=False) as session:
        owner = _owner(session)
        if owner is None:
            return 1
        companies_of = {p.key: p.company for p in PEOPLE}
        for spec in SITES:
            if teams_repository.site_id_for_code(session, spec.code) is not None:
                print(f"{spec.code[:4]}-{spec.code[4:]} 이미 있음, 건너뜀")
                continue
            form = replace(
                spec.form,
                work_start_date=(now.date() - timedelta(days=60)).isoformat(),
                work_end_date=(now.date() + timedelta(days=420)).isoformat(),
            )
            site_id, errors = sites_service.create_site(session, form, owner, now)
            if site_id is None:
                print(f"현장 생성 실패 {spec.code}: {errors}")
                return 1
            joined = (now.date() - timedelta(days=30)).isoformat()
            for company, (category, trade) in COMPANIES.items():
                errors, _ = teams_service.register_participant(
                    session,
                    site_id,
                    owner,
                    ParticipantForm(company, category, trade[:20], "", joined),
                )
                if errors:
                    print(f"업체 등록 실패 {company}: {errors}")
                    return 1
            labels = teams_service.participant_labels(session, site_id)
            ids = {label.split(" · ")[0]: pid for pid, label in labels.items()}
            for p in PEOPLE[4:]:  # 협력업체 담당자만 명부에(계정 연결 없음)
                contact = ContactForm(p.name.split()[0], p.duty[:40])
                teams_service.add_contact(session, site_id, owner, ids[p.company], contact, now)
            added = 0
            for offset, work_type, start, end, place, performer in WORK:
                day = now.date() + timedelta(days=offset)
                if (offset == 0 and start <= f"{now:%H:%M}") or performer is None:
                    continue  # 지난 시각, 실행 업체 없는 예시(지금은 업체가 꼭 있어야 한다)
                performer_id = str(ids[companies_of[performer]])
                first, errors = schedules_service.add_item(
                    session, owner, site_id,
                    WorkItemForm(work_types=(work_type,), work_dates=(day.isoformat(),),
                                 start=start, end=end, location=place,
                                 performing_participant_id=performer_id),
                    now,
                )  # fmt: skip
                if first is None:
                    print(f"작업 실패 {spec.code} {day} {work_type}: {errors}")
                    return 1
                added += 1
            row = teams_repository.join_code(session, site_id)
            assert row is not None  # 현장을 만들 때 생긴다
            row.code = spec.code
            session.commit()
            shown = f"{spec.code[:4]}-{spec.code[4:]}"
            print(f"{shown}  현장 {site_id} · {spec.form.name} · 작업 {added}건")
    print(f"현장 주인(조정자): {OWNER_EMAIL} / {PASSWORD}")
    print("내 계정으로 로그인 → 머리줄 현장 칩 → 현장 추가 → 코드로 참여에 TEST-0000 등을 넣는다.")
    return 0


def _owner(session: Session) -> CurrentUser | None:
    info = auth_service.find_user_by_email(session, OWNER_EMAIL)
    if info is None:
        user_id, errors = auth_service.signup(
            session,
            SignupForm(email=OWNER_EMAIL, display_name="테스트 소장",
                       organization_name="테스트종합건설", password=PASSWORD,
                       phone="01000009999"),
        )  # fmt: skip
        if user_id is None:
            print(f"현장 주인 가입 실패: {errors}")
            return None
        info = auth_service.describe_users(session, [user_id])[user_id]
    return CurrentUser(info.user_id, info.email, info.display_name,
                       info.organization_id, info.organization_name)  # fmt: skip


if __name__ == "__main__":
    raise SystemExit(main())
