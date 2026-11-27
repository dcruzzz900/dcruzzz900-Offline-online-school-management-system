# V126 — Stage 78 / PostgreSQL Migration 151

Added `postgres_migration_151_result_workflow_permissions.py` based on the `result_workflow_permissions` CREATE TABLE definition in `postgres_effective_schema_snapshot.json`.

The migration preserves all eight columns, BIGINT identity primary key, `granted` default, `changed_at` CURRENT_TIMESTAMP default, and UNIQUE (`user_id`, `permission`) constraint. No foreign keys or secondary indexes are added because the source snapshot declares none. The migration is registered only in `postgres_migration_registry.py`; SQLite startup and offline synchronization are unchanged.

Unit tests cover migration identity, consecutive registry registration, source schema fields, defaults, and uniqueness. Live PostgreSQL execution remains untested.
