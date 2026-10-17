"""DB 테스트 공용 준비. TEST_DATABASE_URL(환경 변수 또는 .env)의 PostgreSQL에
마이그레이션을 적용해 쓴다.

TEST_DATABASE_URL이 없으면 DB 테스트는 건너뛴다(건너뜀은 통과가 아니다, docs/setup.md).
외부 API는 가짜 http_get(tests/fakes.py)으로 바꾸고, 현재 시각은 고정한다.
"""

import contextlib
import os
import re
import zlib
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.config import (
    ENV_FILE,
    REPO_ROOT,
    Settings,
    get_settings,
    read_env_file,
    sqlalchemy_url,
)
from app.core.db import get_session
from app.features.forecasts.service import get_http_get
from app.main import create_app
from engine.kst import KST
from tests.fakes import FakeKma

# 14:10 이후라 14시 발표를 받고, 판정 대상은 내일(2026-10-05)이다.
FIXED_NOW = datetime(2026, 10, 4, 15, 0, tzinfo=KST)
TABLES = (
    "site_messages",
    "action_events",
    "action_delegations",
    "action_items",
    "change_revisions",
    "change_cases",
    "judgment_runs",
    "judgments",
    "work_item_revisions",
    "work_items",
    "forecast_runs",
    "mid_forecast_runs",
    "sites",
    "project_memberships",
    "participant_contacts",
    "project_participants",
    "auth_sessions",
    "users",
    "organizations",
)
DEFAULT_PARTNER = "기본 협력업체"
_SCHEDULE_WRITE = re.compile(r"^/schedule(/\d+/edit)?$")


class GongonClient(TestClient):
    """작업 추가·수정에 실행 업체가 없으면 그 현장의 '기본 협력업체'를 붙인다(D-076).

    예전 테스트는 실행 업체 없이 작업을 올렸다. 실행 업체 필수 자체를 보는 테스트는
    performing_participant_id를 직접(빈 값 포함) 넣으면 그대로 보낸다."""

    def post(self, url: Any, *args: Any, **kwargs: Any) -> Any:
        data = kwargs.get("data")
        if (
            isinstance(url, str)
            and _SCHEDULE_WRITE.match(url)
            and isinstance(data, dict)
            and "performing_participant_id" not in data
            and data.get("site_id")
        ):
            kwargs["data"] = {**data, "performing_participant_id": self._partner(data["site_id"])}
        return super().post(url, *args, **kwargs)

    def _partner(self, site_id: Any) -> str:
        pattern = rf'<option value="(\d+)"[^>]*>{DEFAULT_PARTNER}</option>'
        found = re.search(pattern, super().get(f"/schedule?site_id={site_id}").text)
        if found is None:
            super().post(
                f"/sites/{site_id}/participants",
                data={"organization_name": DEFAULT_PARTNER, "category": "subcontractor",
                      "confirm_same_name": "1"},
            )  # fmt: skip
            found = re.search(pattern, super().get(f"/schedule?site_id={site_id}").text)
        return "" if found is None else found.group(1)


# 쓰기 요청은 같은 출처여야 한다(app/core/security.py). TestClient의 기본 호스트와 맞춘다.
SAME_ORIGIN = {"Origin": "http://testserver"}
DEFAULT_USER = {
    "email": "coordinator@example.com",
    "display_name": "테스트 조정자",
    "organization_name": "가상건설",
    "password": "correct-horse-battery",
    "phone": "010-1234-5678",
}


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    raw_url = os.environ.get("TEST_DATABASE_URL") or read_env_file(ENV_FILE).get(
        "TEST_DATABASE_URL", ""
    )
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL 없음: DB 테스트를 실행하지 않음")
    url = sqlalchemy_url(raw_url)
    database = make_url(url).database or ""
    if "test" not in database:
        # 스키마를 지우고 다시 만들기 때문에 개발·운영 DB를 잘못 가리키지 않게 막는다.
        raise RuntimeError(f"테스트 DB 이름에 'test'가 없음: {database!r}")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine: Engine) -> Iterator[Session]:
    with Session(db_engine, expire_on_commit=False) as s:
        yield s
    with db_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def fake_kma() -> FakeKma:
    return FakeKma()


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="", kma_service_key="test-key")


@pytest.fixture
def app(db_engine: Engine, session: Session, fake_kma: FakeKma, settings: Settings) -> FastAPI:
    app = create_app()

    def test_session() -> Iterator[Session]:
        with Session(db_engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[now_kst] = lambda: FIXED_NOW
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_http_get] = lambda: fake_kma
    return app


Browser = Callable[[dict[str, str] | None], TestClient]


@pytest.fixture
def browser(app: FastAPI) -> Iterator[Browser]:
    """브라우저(쿠키가 따로인 TestClient)를 만든다. 사용자 정보를 주면 그 사용자로 가입·로그인한다.

    같은 출처 헤더는 항상 보낸다. 여러 회사 사용자가 같은 현장에 접근하는 검사에 쓴다."""
    with contextlib.ExitStack() as stack:

        def make(user: dict[str, str] | None = None) -> TestClient:
            test_client = stack.enter_context(GongonClient(app, headers=SAME_ORIGIN))
            if user is not None:
                # 휴대폰 번호가 없는 사용자 자료는 이메일로 정한 가상 번호를 붙인다(사람마다 다르게)
                phone = f"010{zlib.crc32(user['email'].encode()) % 10**8:08d}"
                user = {"phone": phone, **user}
                response = test_client.post("/signup", data=user, follow_redirects=False)
                assert response.status_code == 303, response.text
            return test_client

        yield make


@pytest.fixture
def anonymous_client(browser: Browser) -> TestClient:
    """로그인하지 않은 브라우저."""
    return browser(None)


@pytest.fixture
def client(browser: Browser) -> TestClient:
    """가입·로그인한 기본 사용자(DEFAULT_USER, 가상건설)의 브라우저. 기존 화면 테스트가 쓴다."""
    return browser(DEFAULT_USER)


@pytest.fixture
def drop_rules(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """기준표가 없는 공종 처리(기준 미확인 → 판정 안 함)를 시험하려고 일부 공종의 기준을 뺀다.

    2026-10-17(D-080)부터 화면의 모든 공종에 기준이 있어 실제로는 생기지 않지만,
    새 공종을 기준보다 먼저 추가할 때 같은 경로를 탄다.
    """
    from types import MappingProxyType

    import app.core.rules as rules
    import app.features.help.service as help_service
    import app.features.judgments.service as judgments_service

    full = rules.rule_sets_by_label()

    def drop(*labels: str) -> None:
        kept = MappingProxyType({k: v for k, v in full.items() if k not in labels})
        for module in (rules, judgments_service, help_service):
            monkeypatch.setattr(module, "rule_sets_by_label", lambda: kept)

    return drop
