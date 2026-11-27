# Stage 109 — V140 — Migration 180: timetable_entries_v2

Implemented a standalone PostgreSQL-native definition for the effective
`timetable_entries_v2` table: the timetable itself, one row per class, day and slot in a
timetable version.

## Why this table, next

Its two parents, `schools` and `timetable_versions_v2`, are both ported (Migration 173 supplied
the latter).

## What the migration does

Preserves all 18 effective columns. Full DDL and verification are in
`postgres_migration_180_timetable_entries_v2.py`.

- Foreign keys (named, no cascades, matching the source's `NO ACTION`):
  `fk_timetable_entries_v2_school` (`school_id` -> `schools.id`) and
  `fk_timetable_entries_v2_version` (`timetable_version_id` -> `timetable_versions_v2.id`).
  The migration checks `schools.id` is INTEGER and `timetable_versions_v2.id` is BIGINT first.
- Composite UNIQUE `(timetable_version_id, day_id, slot_id, class_id)` is the named constraint
  `uq_timetable_entries_v2_cell`: at most one entry per class and slot in a version. It does not
  include `tenant_id` or `school_id`, exactly as in the source.
- `day_id`, `slot_id`, `class_id`, `arm_id`, `subject_id`, `teacher_id` and `room_id` carry no
  foreign key in the source, so none is added; they are plain BIGINT.
- `entry_type` keeps `DEFAULT 'LESSON'` (free text, no CHECK); `is_fixed` keeps default 0;
  `created_at`/`updated_at` keep `TEXT DEFAULT CURRENT_TIMESTAMP`.
- No CHECK constraints in the source; verification asserts there are none.
- The partial unique `idx_timetable_entries_v2_client_uuid` and the two sync triggers
  (`trg_timetable_entries_v2_sync_defaults` / `_sync_touch`, shared function
  `sync_timetable_entries_v2_fields()`) are recreated and verified.

## Registry and tests

Registered after migration 179. Registry assertions in the 75 earlier migration test files were
advanced mechanically (`range(100, 180)` -> `range(100, 181)`; each `POSTGRES_MIGRATIONS[-k]`
shifted by one). The gap-report test now expects 105 of 113 tables covered and 8 unresolved
(88 columns, 7 foreign keys, 14 indexes); the counts were derived from the schema snapshot and
agree with the regenerated report. `POSTGRES_TABLE_GAP_DETAILS_STAGE109.{md,json}` regenerate it.
New tests: `tests/postgres/test_postgres_migration_180_timetable_entries_v2.py`.

## Verification

- PostgreSQL-focused suite: **679 passed** (667 before + 12 new), run with a local
  stand-in for pytest (no network to install it); please re-run `pytest tests/postgres`.
- Migration registry: **81 migrations**, versions **100-180**.
- Explicit PostgreSQL table definitions: **105 of 113**; remaining: **8**.

Nothing here has been executed against a live PostgreSQL server; the full application regression
suite was not re-run; SQLite startup, SQLite migrations and offline sync are unchanged.

## Queued next

`staff_documents`; `timetable_periods` then `timetable_entries` (legacy tables with tenant-stamp and
tombstone triggers); the `sync_*` group; `schema_steps` (probably not to be ported). See
`POSTGRES_STAGE110_MIGRATION181.md` for the trigger-overlap finding that affects those decisions.
