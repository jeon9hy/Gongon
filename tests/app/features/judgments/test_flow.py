"""현장 등록 → 예보 수집 → 판정 저장 → 화면 조회 흐름. 기상청은 가짜(FakeKma)다."""

import urllib.error
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.features.forecasts.models import ForecastRun
from app.features.judgments.models import Judgment
from tests.fakes import FakeKma

SITE: dict[str, Any] = {
    "name": "○○현장",
    "address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_types": ["철골 작업", "고소작업대"],
}


def add_site(client: TestClient, **changes: Any) -> int:
    location = client.post("/sites", data={**SITE, **changes}, follow_redirects=False).headers[
        "location"
    ]
    return int(location.split("site_id=")[1].split("&")[0])


def run(client: TestClient, site_id: int) -> str:
    response = client.post("/judgments/run", data={"site_id": site_id}, follow_redirects=False)
    assert response.status_code == 303
    return str(response.headers["location"])


def count(session: Session, model: type[Any]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_rain_at_threshold_in_afternoon_gives_stop_review_window(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 13, PCP="1mm 미만")
    fake_kma.set_hour("20261005", 14, PCP="1.0mm")  # 기준과 같음 → 이상에 해당
    fake_kma.set_hour("20261005", 15, PCP="2.0mm")
    site_id = add_site(client)

    page = client.get(run(client, site_id)).text

    assert "판정했습니다" in page
    assert "14:00–16:00" in page
    assert "15:00 강우 예보" in page  # 그래프는 판정을 정한 요소·최댓값 시각으로 연다
    assert "강우 최대 2.0 mm/h (15:00)" in page
    judgment = session.scalars(select(Judgment)).one()
    assert judgment.verdict == "중지 검토"
    assert judgment.rule_source_verified is False
    assert fake_kma.calls[0]["base_time"] == "1400"


def test_work_type_without_rules_is_shown_as_check_and_never_judged(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client)
    page = client.get(run(client, site_id)).text

    assert "판정 기준 확인 전" in page
    assert session.scalars(select(Judgment.work_type)).all() == ["철골 작업"]


def test_site_with_only_unconfirmed_work_types_is_not_judged(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    site_id = add_site(client, work_types=["고소작업대"])

    location = run(client, site_id)

    assert "ran=no_rules" in location
    assert count(session, Judgment) == 0
    assert fake_kma.calls == []


def test_same_issue_and_grid_is_fetched_once_and_not_judged_twice(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    first = add_site(client)
    second = add_site(client, name="△△현장", latitude="37.5667")  # 같은 격자

    run(client, first)
    run(client, first)
    run(client, second)

    assert len(fake_kma.calls) == 1
    assert count(session, ForecastRun) == 1
    assert count(session, Judgment) == 2  # 현장마다 1건, 다시 실행해도 늘지 않음


def test_missing_key_records_unavailable_with_reason_and_retries_later(
    client: TestClient, session: Session, fake_kma: FakeKma, settings: Settings
) -> None:
    object.__setattr__(settings, "kma_service_key", "")
    site_id = add_site(client)

    page = client.get(run(client, site_id)).text

    assert "판정 불가" in page
    assert "기상청 인증키가 설정되지 않음" in page
    assert fake_kma.calls == []

    object.__setattr__(settings, "kma_service_key", "test-key")
    run(client, site_id)
    assert len(fake_kma.calls) == 1  # 실패한 수집은 재사용하지 않고 다시 시도한다
    assert session.scalars(select(ForecastRun.status).order_by(ForecastRun.id)).all() == [
        "failed",
        "success",
    ]


def test_network_failure_is_recorded_not_hidden(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.fail_with = urllib.error.URLError("timed out")
    site_id = add_site(client)

    run(client, site_id)

    judgment = session.scalars(select(Judgment)).one()
    assert judgment.verdict == "판정 불가"
    assert judgment.failure_reason is not None and "연결 실패" in judgment.failure_reason


def test_missing_forecast_value_is_unavailable_not_go(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    del fake_kma.values[("20261005", "1000")]["WSD"]
    site_id = add_site(client)

    run(client, site_id)

    assert session.scalars(select(Judgment.verdict)).one() == "판정 불가"


def test_detail_shows_basis_issue_time_and_pending_source_check(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 9, WSD="10.0")
    run(client, add_site(client))
    judgment_id = session.scalars(select(Judgment.id)).one()

    page = client.get(f"/judgments/{judgment_id}").text

    assert "예보 발표 2026-10-04 14:00 KST" in page
    assert "원문 대조 필요" in page
    assert "산업안전보건기준에 관한 규칙 제383조" in page
    assert "풍속 10.0 → 기준 10 m/s 이상에 해당" in page
    assert "최종 결정은 현장 책임자가 합니다" in page


def test_detail_unknown_id_returns_404(client: TestClient) -> None:
    assert client.get("/judgments/999").status_code == 404


def test_history_filters_by_verdict_and_site(
    client: TestClient, fake_kma: FakeKma, settings: Settings
) -> None:
    fake_kma.set_hour("20261005", 15, PCP="2.0mm")
    first = add_site(client)
    run(client, first)
    object.__setattr__(settings, "kma_service_key", "")
    second = add_site(client, name="△△현장", latitude="35.1796", longitude="129.0756")
    run(client, second)

    unavailable = client.get("/judgments", params={"verdict": "판정 불가"}).text
    only_first = client.get("/judgments", params={"site_id": first}).text

    assert "△△현장" in unavailable and "KMA_SERVICE_KEY" in unavailable
    assert "<td>○○현장</td>" not in unavailable
    assert "<td>△△현장</td>" not in only_first


@pytest.mark.parametrize("params", [{"verdict": "안전"}, {"page": 0}, {"hour": 24}])
def test_out_of_range_query_is_rejected(client: TestClient, params: dict[str, Any]) -> None:
    path = "/dashboard" if "hour" in params else "/judgments"
    assert client.get(path, params=params).status_code == 422


def test_home_without_sites_shows_onboarding_steps(client: TestClient) -> None:
    page = client.get("/").text

    assert "세 단계면 내일 판정을 받습니다" in page
    assert "공온지수" not in page
    assert "발송됨" not in page


def test_home_is_separate_from_site_dashboard_in_menu(client: TestClient) -> None:
    home = client.get("/").text
    dashboard = client.get("/dashboard").text

    assert 'class="rail__logo is-active"' in home
    assert 'href="/dashboard" aria-label="현장 대시보드" aria-current="page"' not in home
    assert 'href="/dashboard" aria-label="현장 대시보드" aria-current="page"' in dashboard


def test_home_summarizes_each_site_and_links_to_its_dashboard(
    client: TestClient, fake_kma: FakeKma
) -> None:
    fake_kma.set_hour("20261005", 15, PCP="2.0mm")
    stop_site = add_site(client, work_types=["철골 작업"])
    add_site(client, name="△△현장", latitude="35.1796", longitude="129.0756",
             work_types=["철골 작업"])  # fmt: skip
    run(client, stop_site)

    page = client.get("/").text

    assert f'href="/dashboard?site_id={stop_site}"' in page
    assert "철골 작업 · 15:00–16:00 · 강우 최대 2.0 mm/h (15:00)" in page
    assert "아직 판정하지 않았습니다" in page  # 두 번째 현장
    assert page.count("site-card--stop") == 1


def test_run_all_judges_every_site_and_fetches_shared_grid_once(
    client: TestClient, session: Session, fake_kma: FakeKma
) -> None:
    add_site(client)
    add_site(client, name="△△현장", latitude="37.5667")  # 같은 격자

    response = client.post("/judgments/run-all", follow_redirects=False)

    assert response.headers["location"] == "/?ran=all_done"
    assert count(session, Judgment) == 2
    assert len(fake_kma.calls) == 1
    assert "전체 현장을 판정했습니다" in client.get(response.headers["location"]).text


def test_run_all_without_sites_says_so(client: TestClient) -> None:
    location = client.post("/judgments/run-all", follow_redirects=False).headers["location"]

    assert location == "/?ran=no_sites"
