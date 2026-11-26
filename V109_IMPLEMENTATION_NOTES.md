# V109 — PostgreSQL table migration 109: announcements

## Reviewed SQLite source

The effective schema snapshot defines `announcements` with 14 columns. The
`school_id` field is nullable because NULL represents a platform-wide
announcement. The table has one non-unique index, `idx_announcements_school_expiry`
on `(school_id, expires_at)`, and declares no foreign keys or triggers.

## PostgreSQL implementation

- Added `postgres_migration_109_announcements.py`.
- Preserved the nullable platform-wide `school_id` behavior.
- Mapped SQLite INTEGER identifiers and integer-valued flags/duration to BIGINT.
- Kept timestamp values as TEXT to avoid changing existing application formatting.
- Recreated the school/expiry lookup index.
- Added schema checks for all 14 columns, index definitions, and absence of
  foreign keys/triggers.
- Registered version 109 in `postgres_migration_registry.py`.
- Added focused DDL/registry tests and updated prior registry-order expectations.

## Scope and validation

This is a standalone PostgreSQL migration only. It does not connect the
PostgreSQL registry to Flask's SQLite startup, alter browser IndexedDB, migrate
existing records, or change application database selection. No live PostgreSQL
server was available for execution of the DDL; actual PostgreSQL catalog and
runtime behavior still require integration testing.
