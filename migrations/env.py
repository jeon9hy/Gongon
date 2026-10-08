"""Alembic 실행 환경. 모델 메타데이터는 각 기능의 models 모듈에서 모은다."""

from alembic import context
from sqlalchemy import create_engine, pool

import app.features.forecasts.models
import app.features.judgments.models
import app.features.schedules.models
import app.features.sites.models  # noqa: F401  (테이블을 메타데이터에 등록)
from app.core.config import get_settings
from app.core.db import Base

target_metadata = Base.metadata


def _url() -> str:
    # 테스트는 config에 URL을 넣어 부른다. 없으면 .env/환경 변수의 DATABASE_URL.
    url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL이 설정되지 않음 (docs/setup.md)")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
