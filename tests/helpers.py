"""여러 화면 테스트가 같이 쓰는 준비 동작.

현장 기본 공종·작업 시간이 없어진 뒤(D-059) 예전 테스트의 '현장 공종을 기본 시간에 판정' 상황은
그 공종·시간의 작업을 내일로 등록해 만든다. 판정 규칙은 그대로이고 작업 연결만 생긴다.
"""

from datetime import date
from typing import Any

from fastapi.testclient import TestClient

TOMORROW = date(2026, 10, 5)  # conftest.FIXED_NOW의 다음 날


def add_site_with_work(client: TestClient, data: dict[str, Any]) -> int:
    """현장을 만들고, data의 work_types·work_start·work_end로 내일 작업을 등록한다.

    내일이 작업 기간 밖이면 작업을 넣지 않는다(기간 밖 날짜는 등록할 수 없다).
    """
    response = client.post("/sites", data=data, follow_redirects=False)
    assert response.status_code == 303, response.text
    site_id = int(response.headers["location"].split("site_id=")[1].split("&")[0])
    start_date = date.fromisoformat(data.get("work_start_date") or "2026-01-01")
    end_date = date.fromisoformat(data.get("work_end_date") or "2099-12-31")
    work_types = data.get("work_types") or []
    if isinstance(work_types, str):
        work_types = [work_types]
    if work_types and start_date <= TOMORROW <= end_date:
        added = client.post(
            "/schedule",
            data={
                "site_id": site_id,
                "work_types": work_types,
                "work_date": TOMORROW.isoformat(),
                "work_dates": TOMORROW.isoformat(),
                "start": data.get("work_start", "07:00"),
                "end": data.get("work_end", "17:00"),
            },
            follow_redirects=False,
        )
        assert added.status_code == 303, added.text
    return site_id
