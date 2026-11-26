import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from build_postgres_immutability_triggers import generate, convert_when, qi


def inventory():
    return json.loads((ROOT / "postgres_trigger_porting_plan.json").read_text())


def test_generates_all_immutability_guards_only():
    sql, count = generate(inventory())
    assert count == 30
    assert sql.count("CREATE TRIGGER ") == 30
    assert "RAISE EXCEPTION '%'" in sql
    assert "History is append-only" in sql


def test_sqlite_null_safe_comparison_is_ported():
    assert convert_when("NEW.x IS OLD.x") == "NEW.x IS NOT DISTINCT FROM OLD.x"
    assert convert_when("NEW.x IS NOT OLD.x") == "NEW.x IS DISTINCT FROM OLD.x"


def test_conditional_immutability_guards_are_preserved():
    sql, _ = generate(inventory())
    assert "OLD.server_recorded_at IS NOT NULL AND NEW.server_recorded_at IS DISTINCT FROM OLD.server_recorded_at" in sql
    assert "OLD.admin_notified = NEW.admin_notified" in sql
    assert "WHEN (TRUE)" in sql


def test_identifiers_are_quoted_and_validated():
    assert qi("score_audit") == '"score_audit"'
    try:
        qi('bad"; DROP TABLE users;--')
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe identifier accepted")


def test_generator_fails_closed_on_unsupported_condition():
    try:
        convert_when("NEW.x > OLD.x")
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported condition accepted")
