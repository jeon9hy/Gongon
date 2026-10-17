"""공온 소개 페이지(2026-10-17): 로그인 없이 열리고, 앱 화면 머리에서 들어갈 수 있다."""

from fastapi.testclient import TestClient


def test_about_opens_without_login(anonymous_client: TestClient) -> None:
    page = anonymous_client.get("/about")

    assert page.status_code == 200
    assert "왜 시작했나" in page.text and "최종 비전" in page.text
    assert 'href="/signup"' in page.text  # 로그인 전에는 시작하기
    assert 'href="/about"' in anonymous_client.get("/welcome").text


def test_signed_in_user_reaches_about_from_the_app_bar(client: TestClient) -> None:
    assert 'class="appbar__about" href="/about"' in client.get("/sites").text
    assert "앱으로 돌아가기" in client.get("/about").text
