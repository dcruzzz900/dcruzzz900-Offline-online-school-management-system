# Stage 98 — V140 — Migration 169: teacher_availability_v2

Implemented a standalone PostgreSQL-native definition for the effective
`teacher_availability_v2` table (when a teacher is or is not available for a
timetable slot: a status, an optional reason and a hard-constraint flag).

## Why this table, next

Its four parents are `schools`, `users`, `school_days_v2` and `schedule_slots`.
Migrations 166 and 168 supplied the last two, so every parent now has an
explicit PostgreSQL definition. It was the first table Stage 97 queued.

## What the migration does

Preserves all 13 effective columns (the SQLite `CREATE TABLE` declares 11;
`client_uuid` and `is_deleted` come from `_make_syncable()`, and the schema
snapshot includes them).

- **Foreign keys** (named, no cascades, matching the source's `NO ACTION`):
  `fk_teacher_availability_v2_school`, `_teacher` (-> `users.id`), `_day`
  (-> `school_days_v2.id`) and `_slot` (-> `schedule_slots.id`).
- **Key types follow the parents.** `school_id` and `teacher_id` stay `INTEGER`
  (`schools.id` and `users.id` are INTEGER); `day_id` and `slot_id` are
  `BIGINT` because the identity keys from migrations 166 and 168 are BIGINT. The
  migration checks all four parent key types before creating anything and
  refuses to run on a mismatch.
- **Composite UNIQUE** `(tenant_id, school_id, teacher_id, day_id, slot_id)`,
  kept as the named constraint `uq_teacher_availability_v2_slot`. Verification
  checks the exact column set and order, and that it is the only UNIQUE
  constraint.
- `availability_status` keeps `DEFAULT 'Available'`; `is_hard_constraint`
  (default 0) and `is_deleted` map to `BIGINT`; `created_at` keeps `TEXT DEFAULT
  CURRENT_TIMESTAMP`. `updated_at` has no default in the source and none here;
  the sync trigger fills it.
- The source has no CHECK constraints (`availability_status` is free text in
  SQLite), so none are added; verification asserts there are none. If the
  application later restricts the status values, that would be a new migration.
- The partial unique `idx_teacher_availability_v2_client_uuid` and the two sync
  triggers (`trg_teacher_availability_v2_sync_defaults` / `_sync_touch`, one
  shared function `sync_teacher_availability_v2_fields()`) are recreated and
  verified, as in 134/166-168. The expected index set is the primary key, the
  UNIQUE constraint's index, and the client UUID index.

## Registry and tests

Registered after migration 168. The registry assertions in the 64 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 169)` -> `range(100, 170)`; each `POSTGRES_MIGRATIONS[-k]` shifted
by one). `tests/postgres/test_stage80_table_gap_report.py` now expects 94 of 113
tables covered and 19 unresolved (250 columns, 22 foreign keys, 32 indexes). Its
known-unresolved example table is now `timetable_rooms_v2`, and it also asserts
that `teacher_availability_v2` is no longer listed.
`POSTGRES_TABLE_GAP_DETAILS_STAGE98.{md,json}` regenerate the report.

New file `tests/postgres/test_postgres_migration_169_teacher_availability_v2.py`
covers: registry position, preserved DDL (all four references, the UNIQUE, no
CHECK), execution of every statement, rejection of a wrong key type for each of
the four parents, and one rejection test per verification step (columns,
foreign keys incl. a partial set, missing or reordered UNIQUE, unexpected CHECK,
indexes, non-partial client UUID index, triggers).

## Verification

- PostgreSQL-focused suite: **554 passed** (540 before + 14 new). pytest was not
  installable in the build environment (no network), so this was run with a
  small local stand-in for the pytest features these tests use; please re-run
  `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **70 migrations**, versions **100-169**.
- Explicit PostgreSQL table definitions: **94 of 113**; remaining: **19**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing
here has been executed against a live PostgreSQL server.

## Queued next

1. `timetable_rooms_v2` (13 columns, FK to `schools`), `timetable_types_v2`
   (10 columns, FK to `schools`) and `timetable_configurations_v2` (19
   columns, no FKs) have no unported parents and can go in any order (Migrations
   170-172).
2. Then re-check which of `timetable_versions_v2`, `timetable_entries_v2`,
   `timetable_conflicts_v2`, `timetable_approvals_v2` and the other
   `timetable_*_v2` tables become unblocked once those three exist.
3. `staff_documents` and the `sync_*` group have no unported parents; the
   `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
   tenant and tombstone helper triggers and should be decided together.
4. `schema_steps` is SQLite's own migration bookkeeping and probably should not
   be ported; confirm before skipping it.
