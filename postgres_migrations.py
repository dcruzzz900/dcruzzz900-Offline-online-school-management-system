"""Small, transactional PostgreSQL migration runner for reviewed migrations.

This runner is intentionally separate from db.py's SQLite migration registry.
It does not translate or execute the existing SQLite migration functions.
Each PostgreSQL migration must be authored and tested for PostgreSQL explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Iterable, Any

from postgres_schema import acquire_migration_lock


@dataclass(frozen=True)
class PostgresMigration:
    version: int
    name: str
    apply: Callable[[Any], None]
    source: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.source.encode("utf-8")).hexdigest()


def _value(row, key: str, index: int = 0):
    if row is None:
        return None
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return row[index]


def _validate_migrations(migrations: Iterable[PostgresMigration]) -> list[PostgresMigration]:
    items = list(migrations)
    versions = [item.version for item in items]
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in versions):
        raise ValueError("PostgreSQL migration versions must be positive integers")
    if len(versions) != len(set(versions)):
        raise ValueError("PostgreSQL migration versions must be unique")
    if any(not item.name.strip() for item in items):
        raise ValueError("PostgreSQL migration names cannot be empty")
    if any(not item.source for item in items):
        raise ValueError("Each migration must provide non-empty source for checksum tracking")
    return sorted(items, key=lambda item: item.version)


def run_postgres_migrations(conn, migrations: Iterable[PostgresMigration], *, lock_key: int = 731_113_001) -> list[int]:
    """Apply pending reviewed migrations under one transaction-scoped lock.

    The caller supplies an open connection. All pending migrations are applied
    atomically in one transaction. Previously applied versions are skipped only
    when their source checksum matches; changed historical migrations fail fast.
    The connection is committed on success and rolled back on any exception.
    """
    items = _validate_migrations(migrations)
    applied_now: list[int] = []
    try:
        acquire_migration_lock(conn, lock_key)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_schema_migrations ("
            "version BIGINT PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "checksum CHAR(64) NOT NULL, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        existing_rows = conn.execute(
            "SELECT version, name, checksum FROM app_schema_migrations ORDER BY version"
        ).fetchall()
        existing = {int(_value(row, "version", 0)): {
            "name": str(_value(row, "name", 1)),
            "checksum": str(_value(row, "checksum", 2)).strip(),
        } for row in existing_rows}

        for migration in items:
            prior = existing.get(migration.version)
            if prior is not None:
                if prior["checksum"] != migration.checksum:
                    raise RuntimeError(
                        f"Applied PostgreSQL migration {migration.version} "
                        f"({prior['name']}) has changed; create a new migration instead"
                    )
                continue

            migration.apply(conn)
            conn.execute(
                "INSERT INTO app_schema_migrations (version, name, checksum) VALUES (?, ?, ?)",
                (migration.version, migration.name, migration.checksum),
            )
            applied_now.append(migration.version)

        conn.commit()
        return applied_now
    except Exception:
        try:
            conn.rollback()
        finally:
            raise
