from pathlib import Path

import pytest

from app.core import config


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u@h/db", "postgresql+psycopg://u@h/db"),
    ],
)
def test_database_url_uses_psycopg_driver(raw: str, expected: str) -> None:
    assert config.sqlalchemy_url(raw) == expected


def test_environment_variable_wins_over_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# 주석\nKMA_SERVICE_KEY='from-file'\nDATABASE_URL=postgresql://f/db\n",
                        encoding="utf-8")  # fmt: skip
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setenv("KMA_SERVICE_KEY", "from-env")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config.get_settings.cache_clear()
    try:
        settings = config.get_settings()
    finally:
        config.get_settings.cache_clear()

    assert settings.kma_service_key == "from-env"
    assert settings.database_url == "postgresql+psycopg://f/db"
