"""설정: 미구성은 조용히 넘어가지 않는다. DB 없음."""

import os

import pytest
from pydantic import SecretStr, ValidationError

from classfit.core.config import Settings
from classfit.database.session import make_engine


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("CLASSFIT_"):
            monkeypatch.delenv(key)


def test_database_url_accepts_only_psycopg() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg://"):
        Settings(_env_file=None, database_url=SecretStr("postgresql+asyncpg://h/db"))


def test_require_database_url_names_the_variable() -> None:
    with pytest.raises(RuntimeError, match="CLASSFIT_DATABASE_URL"):
        Settings(_env_file=None).require_database_url()


def test_missing_returns_env_names_only() -> None:
    assert Settings(_env_file=None).missing("database_url") == ["CLASSFIT_DATABASE_URL"]


def test_literal_rejects_typo_instead_of_silently_off() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="INF")  # type: ignore[arg-type]


def test_cors_wildcard_is_rejected() -> None:
    with pytest.raises(ValidationError, match="\\*"):
        Settings(_env_file=None, cors_origins=["*"])


def test_pool_size_zero_is_rejected() -> None:
    with pytest.raises(ValidationError, match="1 이상"):
        Settings(_env_file=None, db_pool_size=0)


def test_make_engine_rejects_other_drivers() -> None:
    with pytest.raises(RuntimeError, match="postgresql\\+psycopg://"):
        make_engine("postgresql://h/db")
