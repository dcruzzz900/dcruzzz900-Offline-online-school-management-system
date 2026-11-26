# PostgreSQL migration 112 — billing_email_delivery

- Source: `billing_email_delivery` in `postgres_effective_schema_snapshot.json`.
- Columns: 12; own primary key uses BIGINT identity.
- `school_id` uses INTEGER because baseline `schools.id` is INTEGER.
- Preserves `UNIQUE (school_id, event_key)`.
- Preserves the `schools(id)` foreign key.
- Recreates `idx_billing_email_status` and `idx_billing_email_school`.
- Preserves TEXT timestamps and source defaults (`pending`, `0`, `CURRENT_TIMESTAMP`).
- Source table has no triggers; validation rejects unexpected triggers.
- Registered in the standalone PostgreSQL migration registry only.
- No changes to SQLite startup, browser IndexedDB, or offline synchronization.
- Unit tests and Python compilation are required before packaging. No live PostgreSQL
  server is available in this workflow, so actual DDL execution is not claimed.
