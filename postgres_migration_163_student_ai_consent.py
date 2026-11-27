"""Standalone PostgreSQL migration 163 for student AI consent records.

Ports the effective SQLite consent table, its school/status index, and tenant
stamping behaviour. SQLite startup and offline synchronisation are untouched.
"""
from __future__ import annotations

from postgres_migrations import PostgresMigration

MIGRATION_VERSION = 163
MIGRATION_NAME = "create_student_ai_consent"
MIGRATION_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS student_ai_consent (
        student_id BIGINT PRIMARY KEY,
        school_id BIGINT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'granted', 'withdrawn')),
        granted_by_type TEXT,
        granted_by_id BIGINT,
        policy_version TEXT,
        granted_at TEXT,
        withdrawn_at TEXT,
        notes TEXT,
        tenant_id TEXT,
        granted_by_name TEXT,
        relationship TEXT,
        recorded_by BIGINT,
        recorded_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ai_consent_school_status ON student_ai_consent (school_id, status)",
    """CREATE OR REPLACE FUNCTION app_stamp_tenant_student_ai_consent()
    RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE v_tenant_id TEXT;
    BEGIN
        IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
            SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
            NEW.tenant_id := v_tenant_id;
        END IF;
        RETURN NEW;
    END;
    $$""",
    "DROP TRIGGER IF EXISTS trg_student_ai_consent_tenant_stamp_pg ON student_ai_consent",
    "CREATE TRIGGER trg_student_ai_consent_tenant_stamp_pg BEFORE INSERT ON student_ai_consent FOR EACH ROW EXECUTE FUNCTION app_stamp_tenant_student_ai_consent()",
)
MIGRATION_SOURCE = ";\n\n".join(MIGRATION_STATEMENTS)
_EXPECTED_COLUMNS = {
    "student_id": ("bigint", True), "school_id": ("bigint", True),
    "status": ("text", True), "granted_by_type": ("text", False),
    "granted_by_id": ("bigint", False), "policy_version": ("text", False),
    "granted_at": ("text", False), "withdrawn_at": ("text", False),
    "notes": ("text", False), "tenant_id": ("text", False),
    "granted_by_name": ("text", False), "relationship": ("text", False),
    "recorded_by": ("bigint", False), "recorded_at": ("text", False),
}
_EXPECTED_TRIGGERS = {"trg_student_ai_consent_tenant_stamp_pg"}


def apply_student_ai_consent(conn) -> None:
    for statement in MIGRATION_STATEMENTS:
        conn.execute(statement)

    rows = conn.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ? ORDER BY ordinal_position",
        ("student_ai_consent",),
    ).fetchall()
    actual = {
        str(row["column_name"]): (str(row["data_type"]).lower(), str(row["is_nullable"]).upper() == "NO")
        for row in rows
    }
    missing = sorted(set(_EXPECTED_COLUMNS) - set(actual))
    wrong = {name: {"actual": actual[name], "expected": expected}
             for name, expected in _EXPECTED_COLUMNS.items() if name in actual and actual[name] != expected}
    if missing or wrong or set(actual) != set(_EXPECTED_COLUMNS):
        raise RuntimeError(f"student_ai_consent columns incompatible: missing={missing}, wrong={wrong}")

    constraints = conn.execute(
        "SELECT constraint_name, constraint_type FROM information_schema.table_constraints "
        "WHERE table_schema = current_schema() AND table_name = ?", ("student_ai_consent",),
    ).fetchall()
    actual_constraints = {str(r["constraint_name"]): str(r["constraint_type"]).upper() for r in constraints}
    expected_constraints = {
        "student_ai_consent_pkey": "PRIMARY KEY",
        "student_ai_consent_status_check": "CHECK",
    }
    if actual_constraints != expected_constraints:
        raise RuntimeError(f"student_ai_consent constraints incompatible: {actual_constraints}")

    rows = conn.execute(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() AND tablename = ?",
        ("student_ai_consent",),
    ).fetchall()
    indexes = {str(r["indexname"]): str(r["indexdef"]).lower().replace('"', '') for r in rows}
    if set(indexes) != {"student_ai_consent_pkey", "idx_ai_consent_school_status"}:
        raise RuntimeError(f"student_ai_consent indexes incompatible: {sorted(indexes)}")
    if not all(part in indexes["idx_ai_consent_school_status"] for part in ("school_id", "status")):
        raise RuntimeError("student_ai_consent school/status index is incompatible")

    fk_rows = conn.execute(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_schema = current_schema() AND table_name = ? AND constraint_type = 'FOREIGN KEY'",
        ("student_ai_consent",),
    ).fetchall()
    if fk_rows:
        raise RuntimeError("student_ai_consent has unexpected foreign keys")

    trigger_rows = conn.execute(
        "SELECT trigger_name FROM information_schema.triggers "
        "WHERE trigger_schema = current_schema() AND event_object_table = ?", ("student_ai_consent",),
    ).fetchall()
    actual_triggers = {str(r["trigger_name"]) for r in trigger_rows}
    if actual_triggers != _EXPECTED_TRIGGERS:
        raise RuntimeError(f"student_ai_consent triggers incompatible: {sorted(actual_triggers)}")


def migration() -> PostgresMigration:
    return PostgresMigration(version=MIGRATION_VERSION, name=MIGRATION_NAME,
                             apply=apply_student_ai_consent, source=MIGRATION_SOURCE)
