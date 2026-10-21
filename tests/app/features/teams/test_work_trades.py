"""참여 업체가 맡은 업종(D-088, C04-32).

업종은 작업 고르기의 업종 목록에서만 고른다. 작업 고르기는 실행 업체의 업종을 먼저 보이는
거르기일 뿐이라 서버는 업종 밖 작업도 받는다. 가상골조·가상펌프는 합성 시나리오의 가상 회사다.
"""

import re

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.work_kinds import WORK_TRADE_NAMES, trade_key
from app.features.teams import service as teams_service
from tests.app.features.teams.test_roster import add_site, participant_named, register

CONCRETE, EARTH = "철근ㆍ콘크리트공사업", "지반조성ㆍ포장공사업"


def test_trades_are_saved_in_list_order_and_shown_as_the_group_label(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)
    response = client.post(
        f"/sites/{site_id}/participants",
        data={"organization_name": "가상골조", "category": "subcontractor",
              "trade_note": "지하 골조", "work_trades": [CONCRETE, EARTH]},
        follow_redirects=False,
    )  # fmt: skip

    assert response.status_code == 303
    frame = participant_named(session, site_id, "가상골조")
    # 고른 순서가 아니라 업종 목록 순서로 저장한다(지반조성이 목록 앞)
    assert frame.work_trades == sorted([CONCRETE, EARTH], key=WORK_TRADE_NAMES.index)
    # 묶음 줄의 작은 글자는 업종이 메모보다 먼저다
    label = teams_service.company_trades(session, [site_id])[frame.id]
    assert label == " · ".join(frame.work_trades)
    page = client.get(f"/sites/{site_id}/members").text
    assert f'value="{CONCRETE}" checked' in page and "지하 골조" in page


def test_unknown_trade_is_rejected_and_nothing_is_saved(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)

    response = register(client, site_id, "가상펌프", work_trades="펌프카공사업")

    assert response.status_code == 422
    assert "업종은 목록에서 골라 주세요." in response.text
    page = client.get(f"/sites/{site_id}/members").text
    assert "가상펌프" not in page.split('id="dlg-participant"')[0]


def test_editing_without_trades_clears_them_and_falls_back_to_the_note(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)
    register(client, site_id, "가상펌프", trade_note="펌프카", work_trades=CONCRETE)
    pump = participant_named(session, site_id, "가상펌프")

    edited = client.post(
        f"/sites/{site_id}/participants/{pump.id}/edit",
        data={"category": "equipment", "trade_note": "펌프카"},
        follow_redirects=False,
    )

    assert edited.status_code == 303
    pump = participant_named(session, site_id, "가상펌프")
    assert pump.work_trades == []
    assert teams_service.company_trades(session, [site_id])[pump.id] == "펌프카"


def test_add_form_marks_each_performer_with_its_trade_keys_only_when_set(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)
    register(client, site_id, "가상골조", category="subcontractor", work_trades=CONCRETE)
    register(client, site_id, "가상펌프")
    frame = participant_named(session, site_id, "가상골조")
    pump = participant_named(session, site_id, "가상펌프")

    page = client.get(f"/schedule?site_id={site_id}").text

    option = re.search(rf'<option value="{frame.id}"[^>]*>', page)
    assert option is not None and f'data-trades="{trade_key(CONCRETE)}"' in option[0]
    plain = re.search(rf'<option value="{pump.id}"[^>]*>', page)
    assert plain is not None and "data-trades" not in plain[0]
    # 거르기일 뿐 다른 업종 작업도 저장된다(서버는 업종으로 막지 않는다)
    added = client.post(
        "/schedule",
        data={"site_id": site_id, "work_types": "아스팔트 포장", "work_dates": "2026-10-05",
              "start": "09:00", "end": "12:00", "performing_participant_id": frame.id},
        follow_redirects=False,
    )  # fmt: skip
    assert added.status_code == 303
