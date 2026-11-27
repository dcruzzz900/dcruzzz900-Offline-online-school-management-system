# Stage 97 — V140 — Migration 168: schedule_slots

Implemented a standalone PostgreSQL-native definition for the effective
`schedule_slots` table (the timetable's time slots: one row per school day and
bell-schedule period).

## Why this table, next

Stages 95 and 96 ported its two unported parents, `school_days_v2` (166) and
`schedule_templates` (167). Its third parent, `schools`, was already ported. It
is also the parent of `teacher_availability_v2` and of the `timetable_*_v2`
tables that carry a `slot_id`, so porting it now unblocks that family.

## What the migration does

Preserves all 20 effective columns (the SQLite `CREATE TABLE` in `db.py`
declares 18; `client_uuid` and `is_deleted` are added by `_make_syncable()`, and
the schema snapshot includes them).

- **Foreign keys** (named, no cascades, matching the source's `NO ACTION`):
  `fk_schedule_slots_school`, `_day` (-> `school_days_v2.id`) and `_template`
  (-> `schedule_templates.id`).
- **Key types follow the parents.** `school_id` stays `INTEGER` (`schools.id`
  is INTEGER); `day_id` and `schedule_template_id` are `BIGINT` because the
  identity keys created by migrations 166 and 167 are BIGINT. `academic_session_id`
  and `term_id` have no foreign key in the source and are `BIGINT` (as in
  migration 134). The migration checks all three parent key types before
  creating anything and refuses to run on a mismatch.
- **Two CHECK constraints**, now named and verified by name and content:
  `ck_schedule_slots_slot_type` (TEACHING, BREAK, ASSEMBLY, ACTIVITY, OTHER)
  and `ck_schedule_slots_time_order` (`start_time < end_time`). Verification
  uses `pg_get_constraintdef`, as migration 139 does, and fails if any of the
  five slot types is missing from the definition.
- `start_time`/`end_time` stay `TEXT` (the app stores `HH:MM` strings and the
  CHECK compares them as text, exactly as SQLite does).
- Counters and flags (`slot_number`, `duration_minutes`, `is_active`,
  `is_fixed`, `allows_timetable_entry`, `is_deleted`) map to `BIGINT` with the
  source defaults; `slot_type` keeps `DEFAULT 'TEACHING'`; `created_at` and
  `updated_at` keep `TEXT DEFAULT CURRENT_TIMESTAMP`.
- The source has no uniqueness beyond the primary key (unlike
  `teacher_availability_v2`, which has a composite UNIQUE); verification asserts
  there is no UNIQUE constraint.
- The partial unique `idx_schedule_slots_client_uuid` and the two sync triggers
  (`trg_schedule_slots_sync_defaults` / `_sync_touch`, one shared function
  `sync_schedule_slots_fields()`) are recreated and verified, as in 134/166/167.

## Registry and tests

Registered after migration 167. The registry assertions in the 63 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 168)` -> `range(100, 169)`; each `POSTGRES_MIGRATIONS[-k]` shifted
by one). `tests/postgres/test_stage80_table_gap_report.py` now expects 93 of 113
tables covered and 20 unresolved (263 columns, 26 foreign keys, 34 indexes).
Its check that a known-unresolved table appears in the report previously used
`schedule_slots`; it now uses `teacher_availability_v2` and additionally asserts
that `school_days_v2`, `schedule_templates` and `schedule_slots` are no longer
listed. `POSTGRES_TABLE_GAP_DETAILS_STAGE97.{md,json}` regenerate the report.

New file `tests/postgres/test_postgres_migration_168_schedule_slots.py` covers:
registry position, preserved DDL (including both CHECKs and all three
references), execution of every statement, rejection of a wrong parent key type
for each of the three parents, and one rejection test per verification step
(columns, foreign keys incl. a partial set, unexpected UNIQUE, missing CHECKs,
a slot-type CHECK missing a value, a time-order CHECK that does not compare the
two times, indexes, non-partial client UUID index, triggers).

## Verification

- PostgreSQL-focused suite: **540 passed** (525 before + 15 new). pytest was not
  installable in the build environment (no network), so this was run with a
  small local stand-in for the pytest features these tests use; please re-run
  `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **69 migrations**, versions **100-168**.
- Explicit PostgreSQL table definitions: **93 of 113**; remaining: **20**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing
here has been executed against a live PostgreSQL server. The CHECK-definition
verification in particular depends on how PostgreSQL normalises the constraint
text, which is only confirmed against real catalog output (the test fixtures
use the normal form `ANY (ARRAY[...])`).

## Queued next

1. Migration 169: `teacher_availability_v2` (13 columns; FKs to `schools`,
   `users`, `school_days_v2`, `schedule_slots`, all now ported; composite
   UNIQUE `(tenant_id, school_id, teacher_id, day_id, slot_id)`). Check the
   `users.id` key type first.
2. Then `timetable_rooms_v2`, `timetable_types_v2` (FK only to `schools`) and
   `timetable_configurations_v2` (no FKs), which can go in any order, followed
   by the tables that reference them (`timetable_versions_v2`,
   `timetable_entries_v2`, ...).
3. `staff_documents` and the `sync_*` group have no unported parents; the
   `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
   tenant and tombstone helper triggers and should be decided together.
4. `schema_steps` is SQLite's own migration bookkeeping and probably should not
   be ported; confirm before skipping it.
