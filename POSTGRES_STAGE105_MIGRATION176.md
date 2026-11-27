# Stage 105 — V140 — Migration 176: timetable_audit_v2

Implemented a standalone PostgreSQL-native definition for the effective
`timetable_audit_v2` table: the audit trail of timetable actions (who, in which role, did what to which version, with the previous and new status and a reason).

## Why this table, next

Its only foreign key points at `schools`; it is the audit log for the version
workflow ported in Migrations 173-175.

## What the migration does

Preserves all 14 effective columns (the effective-schema snapshot is the
source of truth for this series). Full DDL and verification are in
`postgres_migration_176_timetable_audit_v2.py`.

- Foreign keys (named, no cascades, matching the source's `NO ACTION`): `fk_timetable_audit_v2_school` (`school_id` -> `schools.id`).
- No foreign key on `user_id` or `timetable_version_id`, as in the source.
- No UNIQUE constraint, as in the source.
- Key types: ids that reference a parent follow the parent's type; other ids,
  counters and 0/1 flags map to `BIGINT`; defaults are preserved as in the source.
  The migration checks the parent key types before creating anything (`schools.id` is INTEGER) and refuses to run on a mismatch.
- The source has no CHECK constraints; verification asserts there are none.
- The partial unique `idx_timetable_audit_v2_client_uuid` and the two sync triggers
  (`trg_timetable_audit_v2_sync_defaults` / `_sync_touch`, one shared function
  `sync_timetable_audit_v2_fields()`) are recreated and verified, as in 134 and 166-172.

## Registry and tests

Registered after migration 175. The registry assertions in the 71 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 176)` -> `range(100, 177)`; each `POSTGRES_MIGRATIONS[-k]` shifted by
one). `tests/postgres/test_stage80_table_gap_report.py` now expects 101 of 113 tables
covered and 12 unresolved (140 columns, 16 foreign keys, 21 indexes),
and asserts `timetable_audit_v2` is no longer listed. Those expected counts were derived from the
effective-schema snapshot and agree with the regenerated gap report.
`POSTGRES_TABLE_GAP_DETAILS_STAGE105.{md,json}` regenerate the report.

New file `tests/postgres/test_postgres_migration_176_timetable_audit_v2.py` covers registry
position, preserved DDL, execution of every statement, and one rejection test per
verification step.

## Verification

- PostgreSQL-focused suite: **630 passed** (619 before + 11 new). pytest was not
  installable in the build environment (no network), so this was run with a small
  local stand-in for the pytest features these tests use; please re-run
  `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **77 migrations**, versions **100-176**.
- Explicit PostgreSQL table definitions: **101 of 113**; remaining: **12**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing here
has been executed against a live PostgreSQL server.

## Queued next

- Still queued from this batch: `subject_room_requirements_v2`, `teacher_workload_profiles_v2`, `teacher_timetable_preferences_v2`.
- `timetable_entries_v2` (18 columns; FKs to `timetable_versions_v2` and `schools`,
  both ported) is the largest remaining timetable table and is now unblocked.
- `timetable_periods` (carries tenant-stamp and tombstone triggers beyond the sync
  pair, so it needs extra helper-trigger work) must come before `timetable_entries`.
- `staff_documents` and the `sync_*` group have no unported parents; the
  `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
  tenant and tombstone helper triggers and should be decided together.
- `schema_steps` is SQLite's own migration bookkeeping and probably should not
  be ported; confirm before skipping it.
