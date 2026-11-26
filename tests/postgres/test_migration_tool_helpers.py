import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2] / "tools" / "migrate_sqlite_to_postgres.py"
spec = importlib.util.spec_from_file_location("pg_migrate", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_identifier_quoting():
    assert mod.qi('odd"name') == '"odd""name"'


def test_row_digest_stable_and_bytes_safe():
    assert mod.row_digest([(1, b"abc")]) == mod.row_digest([(1, b"abc")])
    assert mod.row_digest([(1, b"abc")]) != mod.row_digest([(1, b"abd")])


def test_dependency_order_parent_before_child(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "sample.db")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));")
    order = mod.dependency_order(db, ["child", "parent"])
    assert order.index("parent") < order.index("child")
    db.close()


def test_dependency_cycle_fails_closed(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "cycle.db")
    db.executescript("CREATE TABLE a(id INTEGER PRIMARY KEY, b_id INTEGER REFERENCES b(id)); CREATE TABLE b(id INTEGER PRIMARY KEY, a_id INTEGER REFERENCES a(id));")
    try:
        mod.dependency_order(db, ["a", "b"])
        assert False, "cycle should fail closed"
    except RuntimeError as exc:
        assert "cycle" in str(exc).lower()
    db.close()
