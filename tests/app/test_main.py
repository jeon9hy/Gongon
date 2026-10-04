from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import DatabaseNotConfiguredError, get_session
from app.main import create_app


def test_app_starts_and_answers_liveness_check() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_database_setting_shows_setup_page_not_500() -> None:
    app = create_app()

    def no_database() -> Iterator[Session]:
        raise DatabaseNotConfiguredError("DATABASE_URL이 설정되지 않음")
        yield  # 제너레이터 의존성 형태 유지

    app.dependency_overrides[get_session] = no_database

    response = TestClient(app).get("/")

    assert response.status_code == 503
    assert "DB 설정이 필요합니다" in response.text
