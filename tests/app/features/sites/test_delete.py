"""현장 삭제(D-040): 목록·판정·일정에서 빠지고, 지난 판정 내역은 기록으로 남는다."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.features.judgments.models import Judgment
from app.features.sites.models import Site

SITE: dict[str, Any] = {
    "address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start": "07:00",
    "work_end": "17:00",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업"],
}


def add_site(client: TestClient, name: str) -> int:
    location = client.post("/sites", data={**SITE, "name": name}, follow_redirects=False).headers[
        "location"
    ]
    return int(location.split("site_id=")[1].split("&")[0])


def delete(client: TestClient, site_id: int) -> Any:
    return client.post(f"/sites/{site_id}/delete", follow_redirects=False)


def test_deleted_site_leaves_lists_but_its_judgments_stay_in_history(
    client: TestClient, session: Session
) -> None:
    gone = add_site(client, "지울현장")
    kept = add_site(client, "남길현장")
    assert client.post("/judgments/run", data={"site_id": gone}).status_code == 200
    judgment_ids = list(session.scalars(select(Judgment.id).where(Judgment.site_id == gone)))
    assert judgment_ids

    response = delete(client, gone)

    assert response.status_code == 303
    assert "현장을 삭제했습니다" in client.get(response.headers["location"]).text
    home = client.get("/").text
    assert "지울현장" not in home  # 현장 목록과 최근 판정 모두에서 빠진다
    assert "남길현장" in home
    assert "지울현장" not in client.get("/sites").text
    assert "지울현장" not in client.get("/schedule").text
    assert client.get("/dashboard", params={"site_id": gone}).status_code == 404
    assert client.get("/schedule", params={"site_id": gone}).status_code == 404
    # 판정 내역은 지우지 않는다(기록 보관)
    assert len(judgment_ids) == session.scalar(
        select(func.count()).select_from(Judgment).where(Judgment.site_id == gone)
    )
    assert "삭제된 현장" in client.get("/judgments").text
    assert client.get(f"/judgments/{judgment_ids[0]}").status_code == 200
    # 다른 현장은 그대로
    assert client.get("/dashboard", params={"site_id": kept}).status_code == 200


def test_deleted_site_cannot_be_judged_edited_or_deleted_again(client: TestClient) -> None:
    site_id = add_site(client, "지울현장")
    assert delete(client, site_id).status_code == 303

    assert delete(client, site_id).status_code == 404
    assert client.post(f"/sites/{site_id}", data={**SITE, "name": "x"}).status_code == 404
    assert client.get("/sites", params={"site_id": site_id}).status_code == 404
    assert client.post("/judgments/run", data={"site_id": site_id}).status_code == 404


def test_delete_unknown_site_returns_404_and_changes_nothing(
    client: TestClient, session: Session
) -> None:
    site_id = add_site(client, "남길현장")

    assert delete(client, 999).status_code == 404

    assert session.scalar(select(Site.deleted_at).where(Site.id == site_id)) is None
