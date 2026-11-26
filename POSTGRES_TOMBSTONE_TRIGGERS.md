# PostgreSQL sync tombstone triggers (Stage 15)

## Scope

This stage ports all **18 SQLite AFTER DELETE tombstone triggers** across **18 tables**. The generated SQL is in `postgres_tombstone_triggers.sql`.

## Preserved behavior

- A tombstone is written only when the deleted row has a non-NULL `client_uuid`.
- One tombstone is written per deleted row, in the same transaction as the DELETE.
- `entity` is the originating table name and `client_uuid` is copied from `OLD`.
- `school_id` uses the reviewed source mapping: direct `OLD.school_id` or the same class/student/session parent lookup used by SQLite. A missing parent yields NULL, matching the original scalar-subquery behavior and avoiding cross-school delivery.
- `deleted_at` remains UTC text in `YYYY-MM-DDTHH:MM:SS` seconds-resolution format.
- A failed tombstone insert aborts the DELETE transaction, preserving atomicity.

## Safety notes

- The generator accepts only the 18 inventoried table names and known source school-scope mappings; unknown shapes fail closed.
- The trigger function does not issue another DELETE or UPDATE, so it introduces no recursive trigger behavior.
- `sync_tombstones.school_id` is nullable in the inspected effective schema; NULL remains NULL when a parent lookup returns no row.
- This SQL is generated only; it has not been applied to a live PostgreSQL server.
- No changes are made to SQLite local installations or IndexedDB/browser offline behavior.

## Staging validation

Test deletes for each table with NULL and non-NULL client UUIDs, direct and parent-derived school IDs, missing parent rows, multiple-row DELETE statements, and transaction rollback when tombstone insertion fails. Verify the sync pull endpoint filters tombstones by school and advances its cursor correctly.
