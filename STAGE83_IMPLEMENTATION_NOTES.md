# Stage 83 — Migration 154

- Added `postgres_migration_154_result_custom_values.py` for the effective seven-column SQLite table shape from `db.py`.
- Preserved the unique `(student_id, term_id, field_id)` constraint and `updated_at` CURRENT_TIMESTAMP default.
- Source declares no foreign keys, secondary indexes, or triggers; migration does not invent them.
- Registered version 154 in `postgres_migration_registry.py` only.
- Added `tests/postgres/test_postgres_migration_154_result_custom_values.py`.
- No SQLite startup, SQLite migration, database-selection, offline-storage, or offline-sync changes.
- Live PostgreSQL execution was not performed.
