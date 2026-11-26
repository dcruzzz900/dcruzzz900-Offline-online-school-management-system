import pytest

from postgres_dbapi import (
    HybridRow,
    PostgresConnectionAdapter,
    PostgresCursorAdapter,
    hybrid_row_factory,
)


class FakeColumn:
    def __init__(self, name):
        self.name = name


class FakeCursor:
    def __init__(self):
        self.description = [FakeColumn("id"), FakeColumn("school_name")]
        self.calls = []
        self.rows = [(7, "North School")]

    def execute(self, sql, params=None):
        self.calls.append(("execute", sql, params))
        return self

    def executemany(self, sql, params):
        self.calls.append(("executemany", sql, params))
        return self

    def fetchone(self):
        maker = hybrid_row_factory(self)
        return maker(self.rows[0])


class FakeConnection:
    def __init__(self):
        self.cursors = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        cursor = FakeCursor()
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakePoolContext:
    def __init__(self, connection):
        self.connection_obj = connection
        self.exits = 0

    def __enter__(self):
        return self.connection_obj

    def __exit__(self, *args):
        self.exits += 1


class FakePool:
    def __init__(self):
        self.conn = FakeConnection()
        self.context = FakePoolContext(self.conn)

    def connection(self):
        return self.context


def test_hybrid_row_supports_name_and_numeric_indexing():
    row = HybridRow((7, "North School"), ["id", "school_name"])
    assert row[0] == row["id"] == 7
    assert row[1] == row["school_name"] == "North School"
    assert list(row.keys()) == ["id", "school_name"]


def test_cursor_adapter_translates_qmarks_and_returns_cursor_adapter():
    raw = FakeCursor()
    cur = PostgresCursorAdapter(raw)
    assert cur.execute("SELECT * FROM schools WHERE id=?", (7,)) is cur
    assert raw.calls[-1] == ("execute", "SELECT * FROM schools WHERE id=%s", (7,))


def test_cursor_adapter_executemany_translates_markers():
    raw = FakeCursor()
    PostgresCursorAdapter(raw).executemany(
        "INSERT INTO t(a,b) VALUES(?,?)", [(1, 2), (3, 4)]
    )
    assert raw.calls[-1] == (
        "executemany", "INSERT INTO t(a,b) VALUES(%s,%s)", [(1, 2), (3, 4)]
    )


def test_cursor_lastrowid_fails_loudly_and_requires_returning():
    cur = PostgresCursorAdapter(FakeCursor())
    with pytest.raises(NotImplementedError, match="RETURNING"):
        _ = cur.lastrowid


def test_connection_adapter_returns_connection_to_pool_on_close():
    pool = FakePool()
    conn = PostgresConnectionAdapter(pool=pool)
    conn.execute("SELECT ?", (1,))
    conn.commit()
    conn.close()
    assert pool.conn.commits == 1
    assert pool.context.exits == 1
    with pytest.raises(RuntimeError, match="closed"):
        conn.execute("SELECT 1")


def test_connection_context_commits_on_success_and_rolls_back_on_error():
    pool = FakePool()
    with PostgresConnectionAdapter(pool=pool):
        pass
    assert pool.conn.commits == 1

    pool2 = FakePool()
    with pytest.raises(ValueError):
        with PostgresConnectionAdapter(pool=pool2):
            raise ValueError("rollback")
    assert pool2.conn.rollbacks == 1
    assert pool2.context.exits == 1


def test_executescript_is_rejected_explicitly():
    conn = PostgresConnectionAdapter(pool=FakePool())
    with pytest.raises(NotImplementedError, match="SQLite-specific"):
        conn.executescript("CREATE TABLE x(id INTEGER)")
    conn.close()


def test_psycopg_integrity_error_is_mapped_to_sqlite_integrity_error():
    import sqlite3
    from types import SimpleNamespace
    from postgres_dbapi import translate_db_exception

    class PsycopgError(Exception):
        pass

    class PsycopgDatabaseError(PsycopgError):
        pass

    class PsycopgIntegrityError(PsycopgDatabaseError):
        pass

    fake_psycopg = SimpleNamespace(
        IntegrityError=PsycopgIntegrityError,
        OperationalError=type("PsycopgOperationalError", (PsycopgDatabaseError,), {}),
        ProgrammingError=type("PsycopgProgrammingError", (PsycopgDatabaseError,), {}),
        DataError=type("PsycopgDataError", (PsycopgDatabaseError,), {}),
        InterfaceError=type("PsycopgInterfaceError", (PsycopgError,), {}),
        DatabaseError=PsycopgDatabaseError,
        Error=PsycopgError,
    )
    mapped = translate_db_exception(PsycopgIntegrityError("duplicate key"), fake_psycopg)
    assert isinstance(mapped, sqlite3.IntegrityError)
    assert "duplicate key" in str(mapped)


def test_unknown_exception_is_not_mapped():
    from types import SimpleNamespace
    from postgres_dbapi import translate_db_exception

    fake_psycopg = SimpleNamespace(Error=type("PsycopgError", (Exception,), {}))
    assert translate_db_exception(ValueError("bad input"), fake_psycopg) is None


def test_cursor_execute_maps_integrity_errors_for_existing_route_handlers():
    import sqlite3

    class PsycopgIntegrityError(Exception):
        pass

    class RaisingCursor(FakeCursor):
        def execute(self, sql, params=None):
            raise PsycopgIntegrityError("unique constraint")

    # Inject the optional psycopg module at import time for this isolated test.
    import sys
    from types import SimpleNamespace
    fake_psycopg = SimpleNamespace(
        IntegrityError=PsycopgIntegrityError,
        OperationalError=type("PsycopgOperationalError", (Exception,), {}),
        ProgrammingError=type("PsycopgProgrammingError", (Exception,), {}),
        DataError=type("PsycopgDataError", (Exception,), {}),
        InterfaceError=type("PsycopgInterfaceError", (Exception,), {}),
        DatabaseError=type("PsycopgDatabaseError", (Exception,), {}),
        Error=type("PsycopgError", (Exception,), {}),
    )
    previous = sys.modules.get("psycopg")
    sys.modules["psycopg"] = fake_psycopg
    try:
        with pytest.raises(sqlite3.IntegrityError, match="unique constraint"):
            PostgresCursorAdapter(RaisingCursor()).execute("INSERT INTO t(id) VALUES (?)", (1,))
    finally:
        if previous is None:
            sys.modules.pop("psycopg", None)
        else:
            sys.modules["psycopg"] = previous
