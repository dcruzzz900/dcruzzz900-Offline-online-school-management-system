# PostgreSQL migration 110 — attendance_audit

## Reviewed SQLite source

The effective schema snapshot defines `attendance_audit` with 19 columns, one primary key, no declared foreign keys, and one lookup index: `idx_attendance_audit_scope(school_id, subject_type, attendance_date)`. The source also defines CHECK constraints restricting `subject_type` to `student`/`staff` and `action` to `record`/`correct`/`check_in`/`check_out`. Two triggers make the history append-only by rejecting UPDATE and DELETE.

## PostgreSQL implementation

- Added `postgres_migration_110_attendance_audit.py`.
- Uses a BIGINT identity primary key and BIGINT for SQLite INTEGER identifiers.
- Retains TEXT timestamps and a UTC ISO-8601-Z server timestamp default.
- Recreates both CHECK constraints and the lookup index.
- Adds BEFORE UPDATE and BEFORE DELETE guards that raise an exception.
- Validates column names/types/nullability, absence of unexpected foreign keys, expected indexes, CHECK constraints, and both triggers.
- Registered version 110 in `postgres_migration_registry.py`.
- Added migration-specific tests and updated registry-order expectations.

## Scope and validation

This is a standalone PostgreSQL migration only. It is not connected to Flask's SQLite startup, browser IndexedDB, or live data migration. Tests validate the migration definition and registry; a live PostgreSQL server was not available for executing the DDL in this stage.
