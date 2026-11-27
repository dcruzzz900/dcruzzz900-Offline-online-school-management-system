# Stage 102 — V140 — Migration 173: timetable_versions_v2

Implemented a standalone PostgreSQL-native definition for the effective
`timetable_versions_v2` table: numbered versions of a school's timetable (draft, submitted, published, archived), with who created, submitted and published each and an optional link to the version it was revised from.

## Why this table, next

Its only foreign key points at `schools`, so it could be ported as soon as the
leaf tables were done, and `timetable_entries_v2` (which references it) is
blocked until it exists.

## What the migration does

Preserves all 23 effective columns (the effective-schema snapshot is the
source of truth for this series). Full DDL and verification are in
`postgres_migration_173_timetable_versions_v2.py`.

- Foreign keys (named, no cascades, matching the source's `NO ACTION`): `fk_timetable_versions_v2_school` (`school_id` -> `schools.id`).
- `updated_at` has `DEFAULT CURRENT_TIMESTAMP` here (unlike most v2 tables); the
  sync trigger still bumps it on update.
- Composite UNIQUE `(tenant_id, school_id, version_number)` is the named constraint
  `uq_timetable_versions_v2_version_number`.
- `parent_version_id` is a self-reference in spirit only; the source declares no
  foreign key for it, so none is created.
- Key types: ids that reference a parent follow the parent's type; other ids,
  counters and 0/1 flags map to `BIGINT`; defaults are preserved as in the source.
  The migration checks the parent key types before creating anything (`schools.id` is INTEGER) and refuses to run on a mismatch.
- The source has no CHECK constraints; verification asserts there are none.
- The partial unique `idx_timetable_versions_v2_client_uuid` and the two sync triggers
  (`trg_timetable_versions_v2_sync_defaults` / `_sync_touch`, one shared function
  `sync_timetable_versions_v2_fields()`) are recreated and verified, as in 134 and 166-172.

## Registry and tests

Registered after migration 172. The registry assertions in the 68 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 173)` -> `range(100, 174)`; each `POSTGRES_MIGRATIONS[-k]` shifted by
one). `tests/postgres/test_stage80_table_gap_report.py` now expects 98 of 113 tables
covered and 15 unresolved (185 columns, 19 foreign keys, 24 indexes),
and asserts `timetable_versions_v2` is no longer listed. Those expected counts were derived from the
effective-schema snapshot and agree with the regenerated gap report.
`POSTGRES_TABLE_GAP_DETAILS_STAGE102.{md,json}` regenerate the report.

New file `tests/postgres/test_postgres_migration_173_timetable_versions_v2.py` covers registry
position, preserved DDL, execution of every statement, and one rejection test per
verification step.

## Verification

- PostgreSQL-focused suite: **597 passed** (586 before + 11 new). pytest was not
  installable in the build environment (no network), so this was run with a small
  local stand-in for the pytest features these tests use; please re-run
  `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **74 migrations**, versions **100-173**.
- Explicit PostgreSQL table definitions: **98 of 113**; remaining: **15**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing here
has been executed against a live PostgreSQL server.

## Queued next

- Still queued from this batch: `timetable_approvals_v2`, `timetable_conflicts_v2`, `timetable_audit_v2`, `subject_room_requirements_v2`, `teacher_workload_profiles_v2`, `teacher_timetable_preferences_v2`.
- `timetable_entries_v2` (18 columns; FKs to `timetable_versions_v2` and `schools`,
  both ported) is the largest remaining timetable table and is now unblocked.
- `timetable_periods` (carries tenant-stamp and tombstone triggers beyond the sync
  pair, so it needs extra helper-trigger work) must come before `timetable_entries`.
- `staff_documents` and the `sync_*` group have no unported parents; the
  `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
  tenant and tombstone helper triggers and should be decided together.
- `schema_steps` is SQLite's own migration bookkeeping and probably should not
  be ported; confirm before skipping it.
