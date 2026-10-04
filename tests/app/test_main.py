from fastapi.testclient import TestClient

from app.main import create_app


def test_app_starts_and_answers_liveness_check() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
