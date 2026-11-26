import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "sync_trigger_builder", ROOT / "tools" / "build_postgres_sync_timestamp_triggers.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_inventory_covers_all_72_source_triggers_and_36_tables():
    triggers, schema = MOD.load_inputs()
    tables = MOD.validate(triggers, schema)
    assert len(triggers) == 72
    assert len(tables) == 36


def test_generated_sql_uses_before_trigger_to_avoid_self_update_recursion():
    triggers, schema = MOD.load_inputs()
    sql = MOD.generate(MOD.validate(triggers, schema))
    assert sql.count("CREATE TRIGGER trg_") == 36
    assert sql.count("BEFORE INSERT OR UPDATE ON") == 36
    assert "AFTER UPDATE" not in sql
    assert "UPDATE attendance_records SET" not in sql


def test_generated_sql_preserves_legacy_uuid_and_timestamp_formats():
    triggers, schema = MOD.load_inputs()
    sql = MOD.generate(MOD.validate(triggers, schema))
    assert "md5(random()::text || clock_timestamp()::text || pg_backend_pid()::text)" in sql
    assert "YYYY-MM-DD\"T\"HH24:MI:SS" in sql
    assert "IS NOT DISTINCT FROM OLD.updated_at" in sql
    assert "OLD.updated_at::timestamp" in sql
    assert "+ interval '1 second'" in sql


def test_generated_sql_preserves_client_supplied_values():
    triggers, schema = MOD.load_inputs()
    sql = MOD.generate(MOD.validate(triggers, schema))
    assert "IF NEW.client_uuid IS NULL THEN" in sql
    assert "IF NEW.updated_at IS NULL THEN" in sql
    assert "IF NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN" in sql


def test_generator_rejects_unexpected_source_trigger_shape():
    triggers, schema = MOD.load_inputs()
    triggers[0] = dict(triggers[0], source_sql="CREATE TRIGGER unexpected")
    try:
        MOD.validate(triggers, schema)
    except ValueError as exc:
        assert "Unexpected source SQL shape" in str(exc)
    else:
        raise AssertionError("Unexpected source SQL was not rejected")


def test_generator_rejects_missing_sync_column():
    triggers, schema = MOD.load_inputs()
    broken = {**schema, "tables": [dict(t) for t in schema["tables"]]}
    for table in broken["tables"]:
        if table["name"] == "attendance_records":
            table["columns"] = [c for c in table["columns"] if c["name"] != "updated_at"]
    try:
        MOD.validate(triggers, broken)
    except ValueError as exc:
        assert "TEXT client_uuid and updated_at" in str(exc)
    else:
        raise AssertionError("Missing updated_at column was not rejected")
