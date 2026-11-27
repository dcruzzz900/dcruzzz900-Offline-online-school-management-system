# Stage 100 — V140 — Migration 171: timetable_types_v2

Implemented a standalone PostgreSQL-native definition for the effective
`timetable_types_v2` table.

## Why this table, next

It has a single foreign key, to `schools`, and is the second of the three
leaf tables Stage 98 queued. It is ported before `timetable_versions_v2` and the
other tables that may reference a timetable type.

## What the migration does

Preserves all 10 effective columns (the effective-schema snapshot is the source of
truth for this series; in this table the SQLite `CREATE TABLE` already declares
`client_uuid`, `updated_at` and `is_deleted`).

- `status` is nullable with default `'active'` (unlike `timetable_rooms_v2`,
  where it is NOT NULL); this asymmetry is preserved from the source.
- Composite UNIQUE `(tenant_id, school_id, type_code)` is the named constraint
  `uq_timetable_types_v2_type_code`; verification checks the exact column set and
  order, and that it is the only UNIQUE constraint.
- Key types: `school_id` stays `INTEGER` and the migration checks `schools.id` is INTEGER before creating anything; counters and 0/1
  flags map to `BIGINT`; defaults are preserved as in the source.
- The source has no CHECK constraints; verification asserts there are none.
- The partial unique `idx_timetable_types_v2_client_uuid` and the two sync triggers
  (`trg_timetable_types_v2_sync_defaults` / `_sync_touch`, one shared function
  `sync_timetable_types_v2_fields()`) are recreated and verified, as in 134 and 166-169. The
  expected index set is the primary key, the UNIQUE constraint's index and the
  client UUID index.

Full DDL and verification are in `postgres_migration_171_timetable_types_v2.py`.

## Registry and tests

Registered after migration 170. The registry assertions in the 66 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 171)` -> `range(100, 172)`; each `POSTGRES_MIGRATIONS[-k]` shifted by
one). `tests/postgres/test_stage80_table_gap_report.py` now expects 96 of 113 tables
covered and 17 unresolved (227 columns, 20 foreign keys, 28 indexes),
and asserts `timetable_types_v2` is no longer listed.
`POSTGRES_TABLE_GAP_DETAILS_STAGE100.{md,json}` regenerate the report.

New file `tests/postgres/test_postgres_migration_171_timetable_types_v2.py` covers registry
position, preserved DDL, execution of every statement, and one rejection test per
verification step (columns, foreign keys, parent key types, missing or reordered UNIQUE, unexpected CHECK,
indexes, non-partial client UUID index, triggers).

## Verification

- PostgreSQL-focused suite: **576 passed** (565 before + 11 new). pytest was not
  installable in the build environment (no network), so this was run with a small
  local stand-in for the pytest features these tests use; please re-run
  `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **72 migrations**, versions **100-171**.
- Explicit PostgreSQL table definitions: **96 of 113**; remaining: **17**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing here
has been executed against a live PostgreSQL server.

## Queued next

1. Migration 172: `timetable_configurations_v2` (19 columns, no FKs), the last leaf table.
2. Then re-check which of `timetable_versions_v2`, `timetable_entries_v2`,
   `timetable_conflicts_v2`, `timetable_approvals_v2` and the other `timetable_*_v2`
   tables are unblocked.
3. `staff_documents` and the `sync_*` group have no unported parents; the
   `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
   tenant and tombstone helper triggers and should be decided together.
4. `schema_steps` is SQLite's own migration bookkeeping and probably should not
   be ported; confirm before skipping it.
