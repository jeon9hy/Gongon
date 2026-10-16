"""DB 테스트 공용 준비. TEST_DATABASE_URL(환경 변수 또는 .env)의 PostgreSQL에
마이그레이션을 적용해 쓴다.

TEST_DATABASE_URL이 없으면 DB 테스트는 건너뛴다(건너뜀은 통과가 아니다, docs/setup.md).
외부 API는 가짜 http_get(tests/fakes.py)으로 바꾸고, 현재 시각은 고정한다.
"""

import contextlib
import os
from collections.abc import Callable, Iterator
from datetime import datetime

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
    "judgment_runs",
    "judgments",
    "work_item_revisions",
    "work_items",
    "forecast_runs",
    "mid_forecast_runs",
    "sites",
    "project_memberships",
    "project_participants",
    "auth_sessions",
    "users",
    "organizations",
)
# 쓰기 요청은 같은 출처여야 한다(app/core/security.py). TestClient의 기본 호스트와 맞춘다.
SAME_ORIGIN = {"Origin": "http://testserver"}
DEFAULT_USER = {
    "email": "coordinator@example.com",
    "display_name": "테스트 조정자",
    "organization_name": "가상건설",
    "password": "correct-horse-battery",
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
            test_client = stack.enter_context(TestClient(app, headers=SAME_ORIGIN))
            if user is not None:
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
