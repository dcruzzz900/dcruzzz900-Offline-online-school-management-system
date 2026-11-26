# PostgreSQL UTC timestamp defaults (Stage 24)

## Scope

The effective SQLite schema contains four columns whose default is the SQLite-specific expression `strftime('%Y-%m-%dT%H:%M:%SZ','now')`:

- `attendance_audit.server_timestamp`
- `result_publication_audit.server_timestamp`
- `student_ai_consent_events.server_timestamp`
- `student_status_history.server_timestamp`

`tools/build_postgres_timestamp_defaults.py` generates `postgres_timestamp_defaults.sql` for these exact four defaults. It checks the effective schema snapshot and fails closed if the inventory or column types change.

## Conversion semantics

The PostgreSQL default uses `clock_timestamp() AT TIME ZONE 'UTC'` and `to_char` to preserve the existing UTC text representation `YYYY-MM-DDTHH:MM:SSZ`. `clock_timestamp()` is intentional: unlike `CURRENT_TIMESTAMP`, it is evaluated at the time of each row operation rather than remaining fixed at transaction start.

These columns remain `TEXT`, matching the audited effective schema and the existing offline/API representation. This artifact does not convert them to `timestamp with time zone`.

## Apply and validation

1. Create/convert the four tables and confirm their columns are `TEXT`.
2. Review and apply `postgres_timestamp_defaults.sql` in a staging transaction.
3. Insert a row while omitting `server_timestamp`; verify the value ends in `Z` and represents UTC.
4. Insert a row with an explicit timestamp; verify the supplied value is retained.

The SQL is generated but has not been executed against a live PostgreSQL server in this environment. It is not wired into the application startup path. SQLite keeps its original defaults, and IndexedDB/offline sync is unchanged.

## Explicit exclusions

- `CURRENT_TIMESTAMP` expressions already used in application SQL are supported by both SQLite and PostgreSQL, but their textual cast/format may differ; they require column-by-column review before changing data types or API serialization.
- Trigger-generated sync timestamps and tombstones are handled by `postgres_sync_timestamp_triggers.sql` and `postgres_tombstone_triggers.sql` respectively; this file does not duplicate those triggers.
- SQLite schema migration functions in `db.py` remain SQLite-specific and are not made PostgreSQL-compatible by this artifact.
