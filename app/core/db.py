"""DB 연결과 세션. 테이블 변경은 Alembic 마이그레이션(migrations/)으로만 한다."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


class DatabaseNotConfiguredError(RuntimeError):
    """DATABASE_URL이 비어 있다."""


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise DatabaseNotConfiguredError("DATABASE_URL이 설정되지 않음 (docs/setup.md)")
    return create_engine(url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """요청마다 세션 하나. 쓰기는 각 기능 service가 commit한다."""
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        yield session
