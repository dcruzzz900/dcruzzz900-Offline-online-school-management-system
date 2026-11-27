import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = runpy.run_path(str(ROOT / "tools/build_postgres_timestamp_defaults.py"))


def test_timestamp_default_generator_targets_exact_audited_columns():
    snapshot = json.loads((ROOT / "postgres_effective_schema_snapshot.json").read_text())
    sql = GENERATOR["generate"](snapshot)
    assert sql.count("ALTER COLUMN server_timestamp SET DEFAULT") == 4
    for table in (
        "attendance_audit",
        "result_publication_audit",
        "student_ai_consent_events",
        "student_status_history",
    ):
        assert f"ALTER TABLE {table}" in sql
    assert "clock_timestamp() AT TIME ZONE 'UTC'" in sql
    assert "YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"" in sql


def test_timestamp_default_generator_fails_closed_on_schema_drift():
    snapshot = json.loads((ROOT / "postgres_effective_schema_snapshot.json").read_text())
    snapshot["tables"] = [t for t in snapshot["tables"] if t["name"] != "attendance_audit"]
    try:
        GENERATOR["generate"](snapshot)
    except ValueError as exc:
        assert "inventory changed" in str(exc)
    else:
        raise AssertionError("Expected generator to reject changed timestamp inventory")


def test_timestamp_default_generator_rejects_non_text_target():
    snapshot = json.loads((ROOT / "postgres_effective_schema_snapshot.json").read_text())
    table = next(t for t in snapshot["tables"] if t["name"] == "attendance_audit")
    column = next(c for c in table["columns"] if c["name"] == "server_timestamp")
    column["type"] = "TIMESTAMP"
    try:
        GENERATOR["generate"](snapshot)
    except ValueError as exc:
        assert "must remain TEXT" in str(exc)
    else:
        raise AssertionError("Expected generator to reject a changed target type")
