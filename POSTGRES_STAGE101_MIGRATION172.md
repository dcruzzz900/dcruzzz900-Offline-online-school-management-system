# Stage 101 — V140 — Migration 172: timetable_configurations_v2

Implemented a standalone PostgreSQL-native definition for the effective
`timetable_configurations_v2` table.

## Why this table, next

It has no foreign keys and was the third leaf table Stage 98 queued. With it
in place, the three configuration-style leaf tables are done and the larger
`timetable_*_v2` tables can be reassessed.

## What the migration does

Preserves all 19 effective columns (the effective-schema snapshot is the source of
truth for this series; in this table the SQLite `CREATE TABLE` already declares
`client_uuid`, `updated_at` and `is_deleted`).

- No foreign keys, matching the source (not even `school_id`).
- Composite UNIQUE over `(tenant_id, school_id, academic_session_id, term_id)` is
  the named constraint `uq_timetable_configurations_v2_scope`; because two of its
  columns are nullable, NULL scopes are not deduplicated, as in SQLite.
- Defaults of the 10 setting columns are preserved exactly; `solver_time_limit`
  keeps default 30.
- Key types: `school_id` stays `INTEGER` (no foreign key, so no parent check); counters and 0/1
  flags map to `BIGINT`; defaults are preserved as in the source.
- The source has no CHECK constraints; verification asserts there are none.
- The partial unique `idx_timetable_configurations_v2_client_uuid` and the two sync triggers
  (`trg_timetable_configurations_v2_sync_defaults` / `_sync_touch`, one shared function
  `sync_timetable_configurations_v2_fields()`) are recreated and verified, as in 134 and 166-169. The
  expected index set is the primary key, the UNIQUE constraint's index and the
  client UUID index.

Full DDL and verification are in `postgres_migration_172_timetable_configurations_v2.py`.

## Registry and tests

Registered after migration 171. The registry assertions in the 67 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 172)` -> `range(100, 173)`; each `POSTGRES_MIGRATIONS[-k]` shifted by
one). `tests/postgres/test_stage80_table_gap_report.py` now expects 97 of 113 tables
covered and 16 unresolved (208 columns, 20 foreign keys, 26 indexes),
and asserts `timetable_configurations_v2` is no longer listed.
`POSTGRES_TABLE_GAP_DETAILS_STAGE101.{md,json}` regenerate the report.

New file `tests/postgres/test_postgres_migration_172_timetable_configurations_v2.py` covers registry
position, preserved DDL, execution of every statement, and one rejection test per
verification step (columns, foreign keys (including an unexpected one), missing or reordered UNIQUE, unexpected CHECK,
indexes, non-partial client UUID index, triggers).

## Verification

- PostgreSQL-focused suite: **586 passed** (576 before + 10 new). pytest was not
  installable in the build environment (no network), so this was run with a small
  local stand-in for the pytest features these tests use; please re-run
  `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **73 migrations**, versions **100-172**.
- Explicit PostgreSQL table definitions: **97 of 113**; remaining: **16**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing here
has been executed against a live PostgreSQL server.

## Queued next

1. Re-check the 16 remaining table candidates and pick the next ones whose parents
   are all ported: read the foreign keys of `timetable_versions_v2`,
   `timetable_entries_v2`, `timetable_conflicts_v2`, `timetable_approvals_v2`,
   `timetable_audit_v2`, `subject_room_requirements_v2`,
   `teacher_timetable_preferences_v2`, `teacher_workload_profiles_v2`,
   `timetable_periods`, `timetable_entries` before choosing; the earlier survey
   covered only the leaf tables, so which of these are unblocked is not yet verified.
3. `staff_documents` and the `sync_*` group have no unported parents; the
   `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
   tenant and tombstone helper triggers and should be decided together.
4. `schema_steps` is SQLite's own migration bookkeeping and probably should not
   be ported; confirm before skipping it.
