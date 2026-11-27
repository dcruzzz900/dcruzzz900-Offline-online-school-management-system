"""Standalone PostgreSQL migration 159 for per-actor UI preferences.

Ports the effective SQLite table from migration_085_v107_ui_preferences.
This migration does not alter SQLite startup, SQLite migrations, or offline sync.
"""
from __future__ import annotations

from postgres_migrations import PostgresMigration

MIGRATION_VERSION = 159
MIGRATION_NAME = "create_ui_preferences"
MIGRATION_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS ui_preferences (
        kind TEXT NOT NULL,
        actor_id BIGINT NOT NULL,
        school_id BIGINT,
        theme TEXT,
        font_scale BIGINT NOT NULL DEFAULT 100,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (kind, actor_id)
    )""",
)
MIGRATION_SOURCE = ";\n\n".join(MIGRATION_STATEMENTS)
_EXPECTED_COLUMNS = {
    "kind": ("text", True),
    "actor_id": ("bigint", True),
    "school_id": ("bigint", False),
    "theme": ("text", False),
    "font_scale": ("bigint", True),
    "updated_at": ("text", False),
}


def apply_ui_preferences(conn) -> None:
    for statement in MIGRATION_STATEMENTS:
        conn.execute(statement)
    rows = conn.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema=current_schema() AND table_name=? ORDER BY ordinal_position",
        ("ui_preferences",),
    ).fetchall()
    actual = {
        str(row["column_name"]): (str(row["data_type"]).lower(), str(row["is_nullable"]).upper() == "NO")
        for row in rows
    }
    missing = sorted(set(_EXPECTED_COLUMNS) - set(actual))
    wrong = {name: {"actual": actual[name], "expected": expected}
             for name, expected in _EXPECTED_COLUMNS.items() if name in actual and actual[name] != expected}
    if missing or wrong or set(actual) != set(_EXPECTED_COLUMNS):
        raise RuntimeError(f"ui_preferences columns incompatible: missing={missing}, wrong={wrong}")

    constraints = conn.execute(
        "SELECT constraint_name, constraint_type FROM information_schema.table_constraints "
        "WHERE table_schema=current_schema() AND table_name=?", ("ui_preferences",),
    ).fetchall()
    actual_constraints = {str(row["constraint_name"]): str(row["constraint_type"]).upper() for row in constraints}
    if actual_constraints != {"ui_preferences_pkey": "PRIMARY KEY"}:
        raise RuntimeError(f"ui_preferences constraints incompatible: {actual_constraints}")

    indexes = conn.execute(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname=current_schema() AND tablename=?",
        ("ui_preferences",),
    ).fetchall()
    actual_indexes = {str(row["indexname"]): str(row["indexdef"]).lower() for row in indexes}
    if set(actual_indexes) != {"ui_preferences_pkey"}:
        raise RuntimeError(f"ui_preferences indexes incompatible: {sorted(actual_indexes)}")
    if not all(part in actual_indexes["ui_preferences_pkey"] for part in ("kind", "actor_id")):
        raise RuntimeError("ui_preferences composite primary-key index is incompatible")

    triggers = conn.execute(
        "SELECT trigger_name FROM information_schema.triggers "
        "WHERE trigger_schema=current_schema() AND event_object_table=?", ("ui_preferences",),
    ).fetchall()
    if triggers:
        raise RuntimeError("ui_preferences has unexpected triggers")


def migration() -> PostgresMigration:
    return PostgresMigration(version=MIGRATION_VERSION, name=MIGRATION_NAME,
                             apply=apply_ui_preferences, source=MIGRATION_SOURCE)
