"""공온 가이드·내 정보(C04-7, D-064)."""

from fastapi.testclient import TestClient

from tests.conftest import Browser

SITE = {
    "name": "가상A현장",
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
}


def test_guide_and_me_need_login(anonymous_client: TestClient) -> None:
    for path in ("/guide", "/me"):
        response = anonymous_client.get(path, follow_redirects=False)
        assert response.status_code == 303 and "/login" in response.headers["location"]


def test_me_lists_only_my_sites_with_role(client: TestClient, browser: Browser) -> None:
    client.post("/sites", data=SITE)
    other = browser(
        {"email": "other@example.com", "display_name": "남", "organization_name": "남건설",
         "password": "other-password-1"}
    )  # fmt: skip
    other.post("/sites", data={**SITE, "name": "남의현장"})

    page = client.get("/me").text

    assert "가상A현장" in page and "조정자" in page and "남의현장" not in page
    assert "coordinator@example.com" in page


def test_guide_keeps_the_explanations_moved_out_of_screens(client: TestClient) -> None:
    page = client.get("/guide").text

    assert "최종 판단은 현장 책임자가 합니다" in page
    assert "지금 이후 시작" in page and "AI 추천이 아니에요" in page
    assert 'id="gongon-index"' in page and "직전 발표 예보" in page
    assert "업체는 사람 없이 먼저 등록" in page


def test_sources_page_needs_login(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/sources", follow_redirects=False)
    assert response.status_code == 303 and "/login" in response.headers["location"]


def test_sources_page_shows_each_work_type_basis_and_fetched_kcs(client: TestClient) -> None:
    """자료실(개발용, D-079): 기준표·발췌 파일에서 읽은 상태가 공종마다 맞게 보인다."""
    page = client.get("/sources").text
    rows = {
        label: page.split(f"<b>{label}</b>")[1].split("</tr>")[0]
        for label in ("철골 작업", "콘크리트 타설", "도장·방수", "아스팔트 포장", "이동식 크레인")
    }

    assert "원문 확인됨" in rows["철골 작업"] and "법령 API" in rows["철골 작업"]
    assert "원문 대조 필요" in rows["콘크리트 타설"]
    assert "기준 미확보" in rows["도장·방수"] and "KCS 41 47 00" in rows["도장·방수"]
    assert "KCS 44 50 10" in rows["아스팔트 포장"]
    assert "순간풍속" in rows["이동식 크레인"]
    assert "kcs_weather.json" in page and "국가건설기준센터 OpenAPI" in page
    assert 'href="/sources"' in client.get("/guide").text  # 바닥글 자료실 링크
