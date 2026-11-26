# PostgreSQL offline-sync timestamp triggers (Stage 14)

## Scope

This stage ports all **72 SQLite offline-sync timestamp triggers** across **36 tables**. Each table's SQLite `sync_defaults` and `sync_touch` triggers are represented by one PostgreSQL `BEFORE INSERT OR UPDATE` trigger. The generated SQL is in `postgres_sync_timestamp_triggers.sql`.

## Preserved behavior

- On insert, preserve supplied `client_uuid` and `updated_at`; generate only missing values.
- Generated client UUIDs remain 32 lowercase hexadecimal characters, matching the existing SQLite representation. The PostgreSQL implementation uses `md5` over random/time/backend inputs and requires no extension.
- Generated timestamps remain UTC text in `YYYY-MM-DDTHH:MM:SS` format.
- On update, advance `updated_at` only when it is unchanged (including NULL-to-NULL), matching SQLite's `IS` condition.
- If current UTC time is not later than the old timestamp, advance the old timestamp by one second.
- A caller-supplied changed timestamp is preserved.

## Safety and compatibility notes

- The SQL is generated from the trigger inventory and effective schema snapshot; it is not automatically applied.
- The timestamp columns are TEXT in the inspected SQLite-derived effective schema. If the PostgreSQL schema changes these to timestamp types, this SQL must be adapted and revalidated.
- Existing values must use the exact seconds-resolution ISO format when the monotonic fallback is needed; invalid values raise SQLSTATE `22007` rather than silently corrupting sync order.
- The `md5` token preserves the legacy 32-character hex format; it is not intended as an authentication secret.
- This does not change IndexedDB or browser offline-sync code.
- No live PostgreSQL server/driver is available in this environment, so execution against PostgreSQL remains a required integration test.

## Apply sequence

1. Back up the target PostgreSQL database.
2. Confirm all 36 tables and TEXT columns match the effective schema.
3. Apply the SQL in a transaction in staging first.
4. Test inserts with both fields missing, each field supplied independently, updates with unchanged timestamps, caller-supplied changed timestamps, NULL timestamps, and timestamps in the future.
5. Run offline-sync pull/push/conflict tests before production rollout.
