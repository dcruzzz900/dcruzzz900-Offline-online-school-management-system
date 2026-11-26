# Migration 142 implementation notes — rbac_audit_log

Source: `postgres_effective_schema_snapshot.json`, table `rbac_audit_log`, and its associated entries in `other_objects`.

The migration creates the 13-column audit table, its `(school_id, created_at)` lookup index, and the two source append-only triggers. It uses the shared `app_reject_immutable_row` trigger function established by the earlier registered migration 100. Registry order guarantees migration 100 precedes migration 142 in a normal sequential run.

No foreign keys, CHECK constraints, extra unique constraints, or other indexes are introduced. The migration is standalone; it does not modify SQLite startup, application database selection, or browser offline synchronization. A live PostgreSQL server was not available for execution-level verification.
