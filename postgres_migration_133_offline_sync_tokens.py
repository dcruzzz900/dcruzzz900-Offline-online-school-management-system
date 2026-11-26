"""PostgreSQL-native migration 133: offline_sync_tokens.

Ports the offline idempotency-token table without adding undeclared foreign
keys or changing the existing SQLite/offline-sync startup path.
"""
from __future__ import annotations

from postgres_migrations import PostgresMigration

MIGRATION_VERSION = 133
MIGRATION_NAME = "create_offline_sync_tokens"

MIGRATION_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS offline_sync_tokens (
        token TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_id BIGINT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
)
MIGRATION_SOURCE = ";\n\n".join(MIGRATION_STATEMENTS)

_EXPECTED_COLUMNS = {
    "token": ("text", True),
    "entity_type": ("text", True),
    "entity_id": ("bigint", True),
    "created_at": ("text", False),
}


def apply_offline_sync_tokens(conn) -> None:
    for statement in MIGRATION_STATEMENTS:
        conn.execute(statement)

    rows = conn.execute(
        "SELECT column_name, data_type, is_nullable "
        "FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ? "
        "ORDER BY ordinal_position",
        ("offline_sync_tokens",),
    ).fetchall()
    actual = {
        str(row["column_name"]): (
            str(row["data_type"]).lower(),
            str(row["is_nullable"]).upper() == "NO",
        )
        for row in rows
    }
    missing = sorted(set(_EXPECTED_COLUMNS) - set(actual))
    wrong = {
        name: {"actual": actual[name], "expected": expected}
        for name, expected in _EXPECTED_COLUMNS.items()
        if name in actual and actual[name] != expected
    }
    if missing or wrong or set(actual) != set(_EXPECTED_COLUMNS):
        raise RuntimeError(
            "offline_sync_tokens columns incompatible: "
            f"missing={missing}, wrong={wrong}, actual={sorted(actual)}"
        )

    constraint_rows = conn.execute(
        "SELECT constraint_name, constraint_type "
        "FROM information_schema.table_constraints "
        "WHERE table_schema = current_schema() AND table_name = ?",
        ("offline_sync_tokens",),
    ).fetchall()
    constraints = {
        str(row["constraint_name"]): str(row["constraint_type"]).upper()
        for row in constraint_rows
    }
    if constraints != {"offline_sync_tokens_pkey": "PRIMARY KEY"}:
        raise RuntimeError(
            f"offline_sync_tokens constraints incompatible: {constraints}"
        )

    fk_rows = conn.execute(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_schema = current_schema() AND table_name = ? "
        "AND constraint_type = 'FOREIGN KEY'",
        ("offline_sync_tokens",),
    ).fetchall()
    if fk_rows:
        raise RuntimeError("offline_sync_tokens must not have foreign keys")

    index_rows = conn.execute(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = current_schema() AND tablename = ?",
        ("offline_sync_tokens",),
    ).fetchall()
    indexes = {str(row["indexname"]): str(row["indexdef"]).lower() for row in index_rows}
    if set(indexes) != {"offline_sync_tokens_pkey"}:
        raise RuntimeError(
            f"offline_sync_tokens indexes incompatible: {sorted(indexes)}"
        )
    if "unique" not in indexes["offline_sync_tokens_pkey"] or "(token)" not in indexes["offline_sync_tokens_pkey"]:
        raise RuntimeError("offline_sync_tokens primary-key index is incompatible")

    trigger_rows = conn.execute(
        "SELECT trigger_name FROM information_schema.triggers "
        "WHERE trigger_schema = current_schema() AND event_object_table = ?",
        ("offline_sync_tokens",),
    ).fetchall()
    if trigger_rows:
        raise RuntimeError("offline_sync_tokens must not have triggers")


def migration() -> PostgresMigration:
    return PostgresMigration(
        version=MIGRATION_VERSION,
        name=MIGRATION_NAME,
        apply=apply_offline_sync_tokens,
        source=MIGRATION_SOURCE,
    )
