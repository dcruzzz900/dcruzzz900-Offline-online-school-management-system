"""Standalone PostgreSQL migration 162 for per-school AI settings.

Ports the effective SQLite table, including its later tenant_id addition,
without changing SQLite startup, consent handling, or offline sync.
"""
from __future__ import annotations

from postgres_migrations import PostgresMigration

MIGRATION_VERSION = 162
MIGRATION_NAME = "create_school_ai_settings"
MIGRATION_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS school_ai_settings (
        school_id BIGINT PRIMARY KEY,
        enabled BIGINT NOT NULL DEFAULT 0,
        process_student_data BIGINT NOT NULL DEFAULT 0,
        result_analysis BIGINT NOT NULL DEFAULT 1,
        teacher_comments BIGINT NOT NULL DEFAULT 1,
        principal_comments BIGINT NOT NULL DEFAULT 1,
        performance_alerts BIGINT NOT NULL DEFAULT 1,
        ai_tutor BIGINT NOT NULL DEFAULT 1,
        learning_materials BIGINT NOT NULL DEFAULT 1,
        result_assistant BIGINT NOT NULL DEFAULT 0,
        retention_days BIGINT NOT NULL DEFAULT 365,
        privacy_notice_version TEXT NOT NULL DEFAULT '1.0',
        updated_by BIGINT,
        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        tenant_id TEXT
    )""",
)
MIGRATION_SOURCE = ";\n\n".join(MIGRATION_STATEMENTS)
_EXPECTED_COLUMNS = {
    "school_id": ("bigint", True),
    "enabled": ("bigint", True),
    "process_student_data": ("bigint", True),
    "result_analysis": ("bigint", True),
    "teacher_comments": ("bigint", True),
    "principal_comments": ("bigint", True),
    "performance_alerts": ("bigint", True),
    "ai_tutor": ("bigint", True),
    "learning_materials": ("bigint", True),
    "result_assistant": ("bigint", True),
    "retention_days": ("bigint", True),
    "privacy_notice_version": ("text", True),
    "updated_by": ("bigint", False),
    "updated_at": ("timestamp without time zone", False),
    "tenant_id": ("text", False),
}


def apply_school_ai_settings(conn) -> None:
    for statement in MIGRATION_STATEMENTS:
        conn.execute(statement)

    rows = conn.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema=current_schema() AND table_name=? ORDER BY ordinal_position",
        ("school_ai_settings",),
    ).fetchall()
    actual = {
        str(row["column_name"]): (str(row["data_type"]).lower(), str(row["is_nullable"]).upper() == "NO")
        for row in rows
    }
    missing = sorted(set(_EXPECTED_COLUMNS) - set(actual))
    wrong = {name: {"actual": actual[name], "expected": expected}
             for name, expected in _EXPECTED_COLUMNS.items() if name in actual and actual[name] != expected}
    if missing or wrong or set(actual) != set(_EXPECTED_COLUMNS):
        raise RuntimeError(f"school_ai_settings columns incompatible: missing={missing}, wrong={wrong}")

    constraints = conn.execute(
        "SELECT constraint_name, constraint_type FROM information_schema.table_constraints "
        "WHERE table_schema=current_schema() AND table_name=?", ("school_ai_settings",),
    ).fetchall()
    actual_constraints = {str(row["constraint_name"]): str(row["constraint_type"]).upper() for row in constraints}
    if actual_constraints != {"school_ai_settings_pkey": "PRIMARY KEY"}:
        raise RuntimeError(f"school_ai_settings constraints incompatible: {actual_constraints}")

    rows = conn.execute(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname=current_schema() AND tablename=?",
        ("school_ai_settings",),
    ).fetchall()
    indexes = {str(row["indexname"]): str(row["indexdef"]).lower() for row in rows}
    if set(indexes) != {"school_ai_settings_pkey"} or "school_id" not in indexes.get("school_ai_settings_pkey", ""):
        raise RuntimeError(f"school_ai_settings primary-key index incompatible: {sorted(indexes)}")

    foreign_keys = conn.execute(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_schema=current_schema() AND table_name=? AND constraint_type='FOREIGN KEY'",
        ("school_ai_settings",),
    ).fetchall()
    if foreign_keys:
        raise RuntimeError("school_ai_settings has unexpected foreign keys")
    triggers = conn.execute(
        "SELECT trigger_name FROM information_schema.triggers "
        "WHERE trigger_schema=current_schema() AND event_object_table=?",
        ("school_ai_settings",),
    ).fetchall()
    if triggers:
        raise RuntimeError("school_ai_settings has unexpected triggers")


def migration() -> PostgresMigration:
    return PostgresMigration(version=MIGRATION_VERSION, name=MIGRATION_NAME,
                             apply=apply_school_ai_settings, source=MIGRATION_SOURCE)
