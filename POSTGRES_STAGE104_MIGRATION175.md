# Stage 104 — V140 — Migration 175: timetable_conflicts_v2

Implemented a standalone PostgreSQL-native definition for the effective
`timetable_conflicts_v2` table: conflicts the timetable validator found in a version (type, severity, the entity involved, a description and a suggested action, and whether and by whom it was resolved).

## Why this table, next

Its only foreign key points at `schools`; it stores validator output for the
versions ported in Migration 173.

## What the migration does

Preserves all 16 effective columns (the effective-schema snapshot is the
source of truth for this series). Full DDL and verification are in
`postgres_migration_175_timetable_conflicts_v2.py`.

- Foreign keys (named, no cascades, matching the source's `NO ACTION`): `fk_timetable_conflicts_v2_school` (`school_id` -> `schools.id`).
- `entity_type`/`entity_id` is a polymorphic reference and stays unconstrained.
- No UNIQUE constraint, as in the source.
- Key types: ids that reference a parent follow the parent's type; other ids,
  counters and 0/1 flags map to `BIGINT`; defaults are preserved as in the source.
  The migration checks the parent key types before creating anything (`schools.id` is INTEGER) and refuses to run on a mismatch.
- The source has no CHECK constraints; verification asserts there are none.
- The partial unique `idx_timetable_conflicts_v2_client_uuid` and the two sync triggers
  (`trg_timetable_conflicts_v2_sync_defaults` / `_sync_touch`, one shared function
  `sync_timetable_conflicts_v2_fields()`) are recreated and verified, as in 134 and 166-172.

## Registry and tests

Registered after migration 174. The registry assertions in the 70 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 175)` -> `range(100, 176)`; each `POSTGRES_MIGRATIONS[-k]` shifted by
one). `tests/postgres/test_stage80_table_gap_report.py` now expects 100 of 113 tables
covered and 13 unresolved (154 columns, 17 foreign keys, 22 indexes),
and asserts `timetable_conflicts_v2` is no longer listed. Those expected counts were derived from the
effective-schema snapshot and agree with the regenerated gap report.
`POSTGRES_TABLE_GAP_DETAILS_STAGE104.{md,json}` regenerate the report.

New file `tests/postgres/test_postgres_migration_175_timetable_conflicts_v2.py` covers registry
position, preserved DDL, execution of every statement, and one rejection test per
verification step.

## Verification

- PostgreSQL-focused suite: **619 passed** (608 before + 11 new). pytest was not
  installable in the build environment (no network), so this was run with a small
  local stand-in for the pytest features these tests use; please re-run
  `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **76 migrations**, versions **100-175**.
- Explicit PostgreSQL table definitions: **100 of 113**; remaining: **13**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing here
has been executed against a live PostgreSQL server.

## Queued next

- Still queued from this batch: `timetable_audit_v2`, `subject_room_requirements_v2`, `teacher_workload_profiles_v2`, `teacher_timetable_preferences_v2`.
- `timetable_entries_v2` (18 columns; FKs to `timetable_versions_v2` and `schools`,
  both ported) is the largest remaining timetable table and is now unblocked.
- `timetable_periods` (carries tenant-stamp and tombstone triggers beyond the sync
  pair, so it needs extra helper-trigger work) must come before `timetable_entries`.
- `staff_documents` and the `sync_*` group have no unported parents; the
  `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
  tenant and tombstone helper triggers and should be decided together.
- `schema_steps` is SQLite's own migration bookkeeping and probably should not
  be ported; confirm before skipping it.
