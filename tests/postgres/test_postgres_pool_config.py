import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import postgres_pool


def setup_function():
    postgres_pool.close_postgres_pool()


def test_requires_a_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    with pytest.raises(RuntimeError, match="Set DATABASE_URL"):
        postgres_pool.postgres_dsn()


def test_accepts_postgresql_url_without_exposing_it(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://school:secret@localhost/school")
    assert postgres_pool.postgres_dsn().startswith("postgresql://")


def test_rejects_non_postgresql_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///school.db")
    with pytest.raises(ValueError, match="postgresql://"):
        postgres_pool.postgres_dsn()


def test_pool_size_validation(monkeypatch):
    monkeypatch.setenv("PG_POOL_MIN_SIZE", "9")
    monkeypatch.setenv("PG_POOL_MAX_SIZE", "4")
    monkeypatch.setenv("DATABASE_URL", "postgresql://school:secret@localhost/school")
    with pytest.raises(ValueError, match="cannot exceed"):
        postgres_pool.get_postgres_pool()


def test_integer_environment_validation(monkeypatch):
    monkeypatch.setenv("PG_POOL_MAX_SIZE", "many")
    with pytest.raises(ValueError, match="must be an integer"):
        postgres_pool._env_int("PG_POOL_MAX_SIZE", 8)
