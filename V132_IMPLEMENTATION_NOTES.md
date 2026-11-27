# V132 implementation notes — Stage 84 / Migration 155

- Added standalone PostgreSQL migration 155 for `result_display_settings`.
- Ported the effective 57-column source shape from the Stage 83 schema snapshot, including columns introduced by later SQLite migrations.
- Preserved the school_id primary key and source defaults.
- Added structural validation for columns, nullability, primary-key index, foreign keys and triggers.
- Registered migration 155 and added static migration tests.
- SQLite startup, SQLite migrations, database selection, offline storage and offline synchronization were not changed.
- Live PostgreSQL execution was not performed.

## Reconciliation after Migration 155

- Static table-definition coverage: 80 of 113 source tables.
- Remaining table candidates: 33, containing 414 source columns.
- Remaining foreign-key declarations: 36; remaining explicit index declarations: 49.
- These counts are static comparisons only and do not establish live PostgreSQL catalog parity.
