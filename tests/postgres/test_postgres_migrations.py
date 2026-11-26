import hashlib

import pytest

from postgres_migrations import PostgresMigration, run_postgres_migrations


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, applied=()):
        self.applied = list(applied)
        self.calls = []
        self.committed = False
        self.rolled_back = False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "SELECT version, name, checksum" in sql:
            return Result(self.applied)
        if "INSERT INTO app_schema_migrations" in sql:
            self.applied.append({"version": params[0], "name": params[1], "checksum": params[2]})
        return Result()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def migration(version, source="CREATE TABLE example (id BIGINT)", name=None, fn=None):
    return PostgresMigration(version, name or f"migration_{version}", fn or (lambda conn: conn.execute(source)), source)


def test_runner_applies_in_version_order_and_records_checksum():
    conn = FakeConnection()
    applied_order = []
    migrations = [
        migration(2, "CREATE TABLE second (id BIGINT)", fn=lambda c: applied_order.append(2)),
        migration(1, "CREATE TABLE first (id BIGINT)", fn=lambda c: applied_order.append(1)),
    ]
    assert run_postgres_migrations(conn, migrations) == [1, 2]
    assert applied_order == [1, 2]
    records = [params for sql, params in conn.calls if "INSERT INTO app_schema_migrations" in sql]
    assert records[0][2] == hashlib.sha256(migrations[1].source.encode()).hexdigest()
    assert conn.committed and not conn.rolled_back


def test_runner_skips_matching_applied_migration():
    item = migration(1)
    conn = FakeConnection([{"version": 1, "name": item.name, "checksum": item.checksum}])
    assert run_postgres_migrations(conn, [item]) == []
    assert conn.committed


def test_runner_rejects_modified_historical_migration_and_rolls_back():
    conn = FakeConnection([{"version": 1, "name": "migration_1", "checksum": "0" * 64}])
    with pytest.raises(RuntimeError, match="has changed"):
        run_postgres_migrations(conn, [migration(1)])
    assert conn.rolled_back and not conn.committed


def test_runner_rolls_back_if_migration_fails():
    def fail(_conn):
        raise ValueError("bad migration")
    conn = FakeConnection()
    with pytest.raises(ValueError, match="bad migration"):
        run_postgres_migrations(conn, [migration(1, fn=fail)])
    assert conn.rolled_back and not conn.committed


def test_duplicate_versions_rejected_before_database_access():
    conn = FakeConnection()
    with pytest.raises(ValueError, match="unique"):
        run_postgres_migrations(conn, [migration(1), migration(1, source="SELECT 1")])
    assert conn.calls == []


def test_migration_checksum_is_stable():
    item = migration(4, "SELECT 1")
    assert item.checksum == hashlib.sha256(b"SELECT 1").hexdigest()
