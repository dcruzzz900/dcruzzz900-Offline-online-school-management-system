import importlib.util
import sys
import types
from pathlib import Path

from tools.build_postgres_effective_schema_snapshot import build_snapshot, render_markdown

ROOT = Path(__file__).resolve().parents[2]


def _load_db_module_without_optional_werkzeug():
    # db.py only imports Werkzeug's password helper at module load. Migration
    # functions do not call it, so a harmless test stub keeps this test focused
    # on schema execution when the optional web stack is not installed.
    werkzeug = types.ModuleType("werkzeug")
    security = types.ModuleType("werkzeug.security")
    security.generate_password_hash = lambda value: "test-only-hash"
    werkzeug.security = security
    old_werkzeug = sys.modules.get("werkzeug")
    old_security = sys.modules.get("werkzeug.security")
    sys.modules["werkzeug"] = werkzeug
    sys.modules["werkzeug.security"] = security
    try:
        spec = importlib.util.spec_from_file_location("postgres_snapshot_test_db", ROOT / "db.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old_werkzeug is None:
            sys.modules.pop("werkzeug", None)
        else:
            sys.modules["werkzeug"] = old_werkzeug
        if old_security is None:
            sys.modules.pop("werkzeug.security", None)
        else:
            sys.modules["werkzeug.security"] = old_security


def test_snapshot_executes_real_registered_migrations_and_records_final_schema():
    db_module = _load_db_module_without_optional_werkzeug()
    snapshot = build_snapshot(db_module)

    assert snapshot["migration_state"]["schema_version"] == 99
    assert snapshot["migration_state"]["applied_named_steps"] == 76
    assert snapshot["counts"]["tables"] >= 100
    assert snapshot["counts"]["triggers"] >= 100
    assert snapshot["counts"]["columns"] >= 1000
    assert any(table["name"] == "students" for table in snapshot["tables"])
    assert any(table["name"] == "device_credentials" for table in snapshot["tables"])
    assert any(obj["type"] == "trigger" for obj in snapshot["other_objects"])


def test_markdown_snapshot_warns_that_sqlite_ddl_is_not_postgresql():
    db_module = _load_db_module_without_optional_werkzeug()
    snapshot = build_snapshot(db_module)
    report = render_markdown(snapshot)
    assert "not executable PostgreSQL DDL" in report
    assert "Trigger" in report
    assert "students" in report
