# Stage 107 — V140 — Migration 178: teacher_workload_profiles_v2

Implemented a standalone PostgreSQL-native definition for the effective
`teacher_workload_profiles_v2` table: per-teacher workload limits for timetable generation (maximum periods per day and per week, longest run of consecutive periods, and the number of free periods the teacher prefers).

## Why this table, next

Its parents are `schools` and `users`, both ported, and it has no timetable
dependencies.

## What the migration does

Preserves all 12 effective columns (the effective-schema snapshot is the
source of truth for this series). Full DDL and verification are in
`postgres_migration_178_teacher_workload_profiles_v2.py`.

- Foreign keys (named, no cascades, matching the source's `NO ACTION`): `fk_teacher_workload_profiles_v2_school` (`school_id` -> `schools.id`), `fk_teacher_workload_profiles_v2_teacher` (`teacher_id` -> `users.id`).
- Composite UNIQUE `(tenant_id, school_id, teacher_id)` is the named constraint
  `uq_teacher_workload_profiles_v2_teacher`: one profile per teacher per school.
- Defaults of the four workload counters are preserved exactly.
- Key types: ids that reference a parent follow the parent's type; other ids,
  counters and 0/1 flags map to `BIGINT`; defaults are preserved as in the source.
  The migration checks the parent key types before creating anything (`schools.id` is INTEGER; `users.id` is INTEGER) and refuses to run on a mismatch.
- The source has no CHECK constraints; verification asserts there are none.
- The partial unique `idx_teacher_workload_profiles_v2_client_uuid` and the two sync triggers
  (`trg_teacher_workload_profiles_v2_sync_defaults` / `_sync_touch`, one shared function
  `sync_teacher_workload_profiles_v2_fields()`) are recreated and verified, as in 134 and 166-172.

## Registry and tests

Registered after migration 177. The registry assertions in the 73 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 178)` -> `range(100, 179)`; each `POSTGRES_MIGRATIONS[-k]` shifted by
one). `tests/postgres/test_stage80_table_gap_report.py` now expects 103 of 113 tables
covered and 10 unresolved (118 columns, 11 foreign keys, 17 indexes),
and asserts `teacher_workload_profiles_v2` is no longer listed. Those expected counts were derived from the
effective-schema snapshot and agree with the regenerated gap report.
`POSTGRES_TABLE_GAP_DETAILS_STAGE107.{md,json}` regenerate the report.

New file `tests/postgres/test_postgres_migration_178_teacher_workload_profiles_v2.py` covers registry
position, preserved DDL, execution of every statement, and one rejection test per
verification step.

## Verification

- PostgreSQL-focused suite: **655 passed** (643 before + 12 new). pytest was not
  installable in the build environment (no network), so this was run with a small
  local stand-in for the pytest features these tests use; please re-run
  `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **79 migrations**, versions **100-178**.
- Explicit PostgreSQL table definitions: **103 of 113**; remaining: **10**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing here
has been executed against a live PostgreSQL server.

## Queued next

- Still queued from this batch: `teacher_timetable_preferences_v2`.
- `timetable_entries_v2` (18 columns; FKs to `timetable_versions_v2` and `schools`,
  both ported) is the largest remaining timetable table and is now unblocked.
- `timetable_periods` (carries tenant-stamp and tombstone triggers beyond the sync
  pair, so it needs extra helper-trigger work) must come before `timetable_entries`.
- `staff_documents` and the `sync_*` group have no unported parents; the
  `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
  tenant and tombstone helper triggers and should be decided together.
- `schema_steps` is SQLite's own migration bookkeeping and probably should not
  be ported; confirm before skipping it.
