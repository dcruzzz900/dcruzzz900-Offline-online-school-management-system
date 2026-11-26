# Migration 124 — change_audit

Source: `postgres_effective_schema_snapshot.json` from the supplied Stage 50 archive.

The SQLite source defines a 16-column offline change/conflict audit table. The migration uses a BIGINT identity primary key, preserves the school relationship as INTEGER to match the baseline `schools.id`, retains nullable user/server identifiers as INTEGER (the source declares no FK for them), and preserves the server timestamp as TEXT with its source default.

The source's conditional unique index is retained: `(school_id, change_id)` is unique only for non-null change IDs whose outcome is `applied`, `merged`, or `latest_wins`. Two additional lookup indexes are recreated. No source triggers are declared.

This is a standalone PostgreSQL migration. It does not connect PostgreSQL to SQLite startup or change existing offline synchronization behavior. Live PostgreSQL execution has not been performed as part of this stage.
