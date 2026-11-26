# Migration 126 — custom_field_options

Source: `postgres_effective_schema_snapshot.json` from the Stage 52 archive.

The source table has seven columns: `id`, `field_id`, `school_id`, `tenant_id`, `option_value`, `display_order`, and `is_active`. It declares a composite UNIQUE constraint on `(field_id, option_value)` and no foreign keys, additional indexes, or triggers.

The standalone PostgreSQL migration uses a BIGINT identity primary key, maps SQLite INTEGER columns to BIGINT, preserves TEXT values and source defaults, and recreates the composite uniqueness rule. Its apply function validates column names/types/nullability, the exact primary/unique index set, and absence of foreign keys and triggers.

The migration is registered as version 126. It is not imported by `db.py`, does not switch application database startup, and does not change SQLite or browser offline-sync behavior. Live PostgreSQL DDL execution has not been performed in this stage.
