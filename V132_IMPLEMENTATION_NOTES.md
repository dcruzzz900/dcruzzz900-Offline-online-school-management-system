# Migration 132 — device_credentials

## Source review

The effective SQLite schema snapshot contains 14 columns, two foreign keys (to `schools.id` and `users.id`), three explicit non-unique lookup indexes, an inline unique constraint on `device_id`, and one AFTER INSERT trigger named `trg_device_credentials_tenant_stamp`.

## PostgreSQL mapping

- `id`: BIGINT identity primary key.
- `school_id`, `user_id`: INTEGER, matching the baseline `schools.id` and `users.id` types.
- Other SQLite INTEGER field `revoked`: BIGINT with source default `0`.
- TEXT fields remain TEXT, including `issued_at` with `CURRENT_TIMESTAMP` default.
- `device_id` remains unique.

## Trigger behavior

When an inserted credential has a NULL or empty `tenant_id`, the trigger updates the inserted row with the `tenant_id` belonging to its referenced school. An explicitly supplied non-empty tenant ID is preserved, matching the source trigger condition.

## Scope and validation

Migration 132 is registered in the standalone PostgreSQL migration runner. It is not imported by `db.py`, does not alter SQLite startup, and does not modify browser IndexedDB or offline synchronization. Automated tests validate DDL structure and catalog-validation behavior. A live PostgreSQL server was not available for executing the DDL or checking trigger behavior against a real catalog.
