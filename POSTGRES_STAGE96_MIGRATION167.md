# Stage 96 — V140 — Migration 167: schedule_templates

Implemented a standalone PostgreSQL-native definition for the effective
`schedule_templates` table (named bell-schedule templates; the application
creates one default "Standard School Schedule" per school).

## Why this table, next

It is the second of the two leaf dependencies Stage 94 queued for
`schedule_slots`. Its three foreign keys (`schools`, `sessions`, `terms`) all
point at tables that already have explicit PostgreSQL definitions, so it can be
ported on its own. With Migration 166 (`school_days_v2`) and this one in place,
`schedule_slots` has no unported parents left.

## What the migration does

Preserves all 13 effective columns: `id`, `tenant_id`, `school_id`,
`academic_session_id`, `term_id`, `name`, `description`, `is_default`,
`status`, `created_at`, `updated_at`, `client_uuid`, `is_deleted`. As with
`school_days_v2`, the SQLite `CREATE TABLE` in `db.py` declares only the first
eleven; `client_uuid` and `is_deleted` are added by `_make_syncable()`, and the
effective-schema snapshot (the source of truth for this series) includes them.

- `school_id`, `academic_session_id` and `term_id` stay `INTEGER`, matching
  the INTEGER primary keys of `schools`, `sessions` and `terms`. The migration
  checks all three parent key types before creating anything and refuses to run
  on a mismatch. (Migration 134 declared `academic_session_id`/`term_id` as
  BIGINT only because that table has no foreign keys on them.)
- Three named foreign keys, no cascades, matching the source's `NO ACTION`:
  `fk_schedule_templates_school`, `_session` and `_term`.
- `is_default` (default 0) and `is_deleted` map to `BIGINT`; `status` keeps
  `DEFAULT 'active'`; `created_at`/`updated_at` keep `TEXT DEFAULT
  CURRENT_TIMESTAMP`, the convention in migrations 129 and 165.
- The source has no uniqueness besides the primary key; verification asserts
  there is no UNIQUE constraint. (Several templates per school are allowed; the
  application picks the default by `ORDER BY is_default DESC, id`.)
- The partial unique `idx_schedule_templates_client_uuid` and the two sync
  triggers (`trg_schedule_templates_sync_defaults` / `_sync_touch`, one shared
  function `sync_schedule_templates_fields()`) are recreated and verified,
  following migrations 134 and 166.

## Registry and tests

Registered after migration 166. The registry assertions in the 62 earlier
`tests/postgres/test_postgres_migration_*.py` files were advanced mechanically
(`range(100, 167)` → `range(100, 168)`, each `POSTGRES_MIGRATIONS[-k]` shifted
by one). `tests/postgres/test_stage80_table_gap_report.py` now expects 92 of 113
tables covered and 21 unresolved (283 columns, 29 foreign keys, 35 indexes);
`POSTGRES_TABLE_GAP_DETAILS_STAGE96.{md,json}` regenerate the report.

Twelve new checks are in
`tests/postgres/test_postgres_migration_167_schedule_templates.py`: registry
position, preserved DDL, execution of every statement, a rejection test for
each of the three parent key types, and one for each verification step
(columns, foreign keys including a partial set, unexpected UNIQUE, indexes,
non-partial client UUID index, triggers).

## Verification

- PostgreSQL-focused suite: **525 passed** (513 before + 12 new). pytest was
  not installable in the build environment (no network), so this was run with
  a small local stand-in for the pytest features these tests use; please
  re-run `pytest tests/postgres` on your side.
- Python compilation: passed (whole package).
- Migration registry: **68 migrations**, versions **100–167**.
- Explicit PostgreSQL table definitions: **92 of 113**; remaining: **21**.

The full application regression suite (including Playwright tests) was not
re-run. SQLite startup, SQLite migrations, IndexedDB storage and offline
synchronization are unchanged. As for every migration in this series, nothing
here has been executed against a live PostgreSQL server.

## Queued next

1. Migration 168: `schedule_slots` (20 columns; FKs to `schools`,
   `school_days_v2`, `schedule_templates`; two CHECK constraints on
   `slot_type` and `start_time < end_time`; sync columns/triggers).
2. Then `teacher_availability_v2` and the other `timetable_*_v2` tables.
3. `staff_documents` and the `sync_*` group have no unported parents; the
   `sync_conflicts`/`sync_log`/`sync_tombstones` tables also interact with the
   tenant and tombstone helper triggers and should be decided together.
4. `schema_steps` is SQLite's own migration bookkeeping and probably should not
   be ported; confirm before skipping it.
