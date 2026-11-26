import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "tombstone_builder", ROOT / "tools" / "build_postgres_tombstone_triggers.py"
)
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def inputs():
    triggers, schema = BUILDER.load_inputs()
    tables = BUILDER.validate(triggers, schema)
    return triggers, schema, tables


def test_all_18_sqlite_tombstone_triggers_are_accounted_for():
    triggers, _, tables = inputs()
    assert len(triggers) == 18
    assert len(tables) == 18
    assert set(tables) == set(BUILDER.SCHOOL_SCOPE)


def test_generated_sql_has_one_after_delete_trigger_per_table():
    _, _, tables = inputs()
    sql = BUILDER.generate(tables)
    assert sql.count("CREATE TRIGGER trg_") == 18
    assert sql.count("AFTER DELETE ON") == 18
    assert sql.count("WHEN (OLD.client_uuid IS NOT NULL)") == 18
    assert "EXECUTE FUNCTION app_record_sync_tombstone();" in sql


def test_generated_sql_preserves_tombstone_payload_and_utc_format():
    _, _, tables = inputs()
    sql = BUILDER.generate(tables)
    assert "INSERT INTO sync_tombstones (school_id, entity, client_uuid, deleted_at)" in sql
    assert "VALUES (v_school_id, TG_TABLE_NAME, OLD.client_uuid, v_deleted_at)" in sql
    assert "YYYY-MM-DD\"T\"HH24:MI:SS" in sql
    assert "IF OLD.client_uuid IS NULL THEN" in sql
    assert "RETURN OLD;" in sql


def test_parent_lookups_keep_missing_parent_null_semantics():
    _, _, tables = inputs()
    sql = BUILDER.generate(tables)
    assert "SELECT school_id FROM classes WHERE id = OLD.class_id INTO v_school_id;" in sql
    assert "SELECT school_id FROM sessions WHERE id = OLD.session_id INTO v_school_id;" in sql
    assert "SELECT c.school_id FROM students s JOIN classes c ON c.id = s.class_id WHERE s.id = OLD.student_id INTO v_school_id;" in sql


def test_generator_rejects_unreviewed_trigger_sql():
    triggers, schema = BUILDER.load_inputs()
    triggers[0] = dict(triggers[0], source_sql=triggers[0]["source_sql"].replace("OLD.client_uuid", "OLD.other_uuid"))
    try:
        BUILDER.validate(triggers, schema)
    except ValueError:
        pass
    else:
        raise AssertionError("Unreviewed trigger SQL must be rejected")
