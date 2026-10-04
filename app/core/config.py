"""환경 변수는 여기서만 읽는다. 루트의 .env도 읽되, 이미 설정된 환경 변수가 우선한다."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    kma_service_key: str


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def sqlalchemy_url(database_url: str) -> str:
    """postgresql:// 형식(Supabase 등이 주는 형식)을 psycopg 3 드라이버 URL로 바꾼다."""
    for prefix in ("postgresql://", "postgres://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url[len(prefix) :]
    return database_url


@lru_cache
def get_settings() -> Settings:
    file_values = read_env_file(ENV_FILE)

    def value(name: str) -> str:
        return os.environ.get(name) or file_values.get(name, "")

    return Settings(
        database_url=sqlalchemy_url(value("DATABASE_URL")),
        kma_service_key=value("KMA_SERVICE_KEY"),
    )
