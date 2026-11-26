# Migration 128 — class_timetable_preferences_v2

## Source review

Reviewed `class_timetable_preferences_v2` in `postgres_effective_schema_snapshot.json` from the Stage 54 archive. The source table contains 15 columns, two declared foreign keys (`school_id` to `schools.id`, `class_id` to `classes.id`), one partial unique client UUID index, and two synchronization triggers.

## PostgreSQL implementation

- Uses a BIGINT identity primary key.
- Preserves `school_id` and `class_id` as INTEGER to match the referenced baseline primary keys.
- Maps other SQLite INTEGER fields to BIGINT and retains text payload/timestamp fields as TEXT.
- Preserves the `active` status default and `is_deleted` default of 0.
- Recreates the partial unique index on non-null `client_uuid` values.
- Replaces SQLite AFTER triggers with PostgreSQL BEFORE INSERT/UPDATE trigger logic. Inserts generate a client UUID and timestamp when missing; updates advance `updated_at` when the caller has not changed it, including a one-second monotonic increment when necessary.
- Validates dependencies, columns/nullability, exact foreign-key set, index set/definition, and trigger names.

## Scope

This is a standalone PostgreSQL migration. It is not imported by SQLite startup and does not change the existing SQLite or browser offline-sync implementation. No live PostgreSQL server was available for execution/catalog validation in this stage.
