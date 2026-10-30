"""목록 화면의 쿼리 수(architecture §6 조회 범위). 가상 현장·가상 회사만 쓴다.

작업이 늘어도 같은 화면의 SQL 문장 수는 같아야 한다(N+1 없음). 현장별로 따로 읽는 부분은 있어
현장 수에는 비례하지만(사용자당 현장은 몇 곳), 현장 하나가 늘 때의 증가량에 상한을 둔다.
2026-10-30 측정: 현장 1곳 홈 32·일정 19·판정 15·변경 4·조치 9·업체 10·대화 4, 현장 하나에 +2~+9.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient

from tests.helpers import TOMORROW, add_site_with_work

SITE: dict[str, Any] = {
    "road_address": "서울 중구 세종대로 110",
    "latitude": "37.5665",
    "longitude": "126.9780",
    "work_start_date": "2026-10-01",
    "work_end_date": "2026-12-31",
    "work_types": ["철골 작업"],
    "work_start": "09:00",
    "work_end": "12:00",
}
PAGES = ("/home", "/schedule", "/dashboard", "/changes", "/actions", "/team", "/chat")
PER_SITE_MAX = 10  # 현장 하나가 늘 때 한 화면에서 더 나가도 되는 문장 수

Counter = Callable[[], AbstractContextManager[list[str]]]


def add_work(client: TestClient, site_id: int, days: int) -> None:
    dates = [(TOMORROW + timedelta(days=n)).isoformat() for n in range(days)]
    response = client.post(
        "/schedule",
        data={
            "site_id": site_id,
            "work_types": ["철골 작업", "콘크리트 타설"],
            "work_date": dates[0],
            "work_dates": dates,
            "start": "13:00",
            "end": "16:00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def query_counts(client: TestClient, count_queries: Counter) -> dict[str, int]:
    counts = {}
    for page in PAGES:
        client.get(page)  # 공휴일·기준표 같은 프로세스 캐시를 먼저 채운다
        with count_queries() as statements:
            response = client.get(page)
        assert response.status_code == 200, page
        counts[page] = len(statements)
    return counts


def test_more_work_items_do_not_add_queries(client: TestClient, count_queries: Counter) -> None:
    site_id = add_site_with_work(client, {**SITE, "name": "가상A현장"})
    before = query_counts(client, count_queries)
    add_work(client, site_id, days=4)  # 작업 1건 → 9건
    assert query_counts(client, count_queries) == before


def test_queries_grow_at_most_a_fixed_amount_per_site(
    client: TestClient, count_queries: Counter
) -> None:
    add_site_with_work(client, {**SITE, "name": "가상A현장"})
    one_site = query_counts(client, count_queries)
    for name in ("가상B현장", "가상C현장", "가상D현장"):
        add_site_with_work(client, {**SITE, "name": name})
    four_sites = query_counts(client, count_queries)
    grown = {page: four_sites[page] - one_site[page] for page in PAGES}
    assert all(n <= 3 * PER_SITE_MAX for n in grown.values()), grown
