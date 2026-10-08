"""DB 테스트 공용 준비. TEST_DATABASE_URL(환경 변수 또는 .env)의 PostgreSQL에
마이그레이션을 적용해 쓴다.

TEST_DATABASE_URL이 없으면 DB 테스트는 건너뛴다(건너뜀은 통과가 아니다, docs/setup.md).
외부 API는 가짜 http_get(tests/fakes.py)으로 바꾸고, 현재 시각은 고정한다.
"""

import os
from collections.abc import Iterator
from datetime import datetime

import pytest
from alembic import command
from alembic.config import Config
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
TABLES = ("judgments", "work_items", "forecast_runs", "mid_forecast_runs", "sites")


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
def client(
    db_engine: Engine, session: Session, fake_kma: FakeKma, settings: Settings
) -> Iterator[TestClient]:
    app = create_app()

    def test_session() -> Iterator[Session]:
        with Session(db_engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[now_kst] = lambda: FIXED_NOW
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_http_get] = lambda: fake_kma
    with TestClient(app) as test_client:
        yield test_client
