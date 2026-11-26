"""Optional PostgreSQL connection-pool foundation for School Result System.

This module is deliberately separate from db.get_db(): the current application
contains SQLite-specific migrations and SQL throughout its route modules.  Do
not route production traffic here until the PostgreSQL compatibility and
migration phases in MIGRATION_POSTGRES.md have passed their acceptance tests.

SQLite/local installs do not import psycopg and remain unaffected.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator, Any

_pool = None
_pool_lock = threading.Lock()


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 1000) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def postgres_dsn() -> str:
    """Return the configured DSN without logging or exposing its credentials."""
    dsn = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN") or "").strip()
    if not dsn:
        raise RuntimeError("Set DATABASE_URL (or POSTGRES_DSN) to enable PostgreSQL")
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL must use postgresql:// or postgres://")
    return dsn


def get_postgres_pool(*, open_pool: bool = True):
    """Create (once) and return a psycopg 3 pool.

    Defaults are conservative for a single application process.  Size the
    aggregate max across all Gunicorn workers below PostgreSQL's connection
    budget (and below PgBouncer's client/server limits where applicable).
    """
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        dsn = postgres_dsn()
        min_size = _env_int("PG_POOL_MIN_SIZE", 1, 0, 100)
        max_size = _env_int("PG_POOL_MAX_SIZE", 8, 1, 500)
        if min_size > max_size:
            raise ValueError("PG_POOL_MIN_SIZE cannot exceed PG_POOL_MAX_SIZE")
        timeout = _env_int("PG_POOL_TIMEOUT", 10, 1, 300)
        try:
            from psycopg_pool import ConnectionPool
            from postgres_dbapi import hybrid_row_factory
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires psycopg[binary] and psycopg-pool; "
                "install requirements-postgres.txt"
            ) from exc

        kwargs: dict[str, Any] = {
            "conninfo": dsn,
            "min_size": min_size,
            "max_size": max_size,
            "timeout": timeout,
            "kwargs": {
                "row_factory": hybrid_row_factory,
                # Compatible with transaction-pooling PgBouncer deployments.
                "prepare_threshold": 0,
                "connect_timeout": _env_int("PG_CONNECT_TIMEOUT", 10, 1, 120),
            },
            "open": open_pool,
        }
        _pool = ConnectionPool(**kwargs)
        if open_pool:
            _pool.wait(timeout=timeout)
        return _pool


@contextmanager
def postgres_connection() -> Iterator[Any]:
    """Borrow a pooled connection; it is returned to the pool on exit."""
    pool = get_postgres_pool()
    with pool.connection() as conn:
        yield conn


def postgres_healthcheck() -> bool:
    """Verify a real database round trip. Raises on configuration/connectivity errors."""
    with postgres_connection() as conn:
        row = conn.execute("SELECT 1 AS healthy").fetchone()
        return bool(row and row["healthy"] == 1)


def close_postgres_pool() -> None:
    """Close the process pool cleanly (e.g. during controlled shutdown/tests)."""
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.close()
