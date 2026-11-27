# Stage 95 — V140 — Migration 166: school_days_v2

Implemented a standalone PostgreSQL-native definition for the effective
`school_days_v2` table (the per-school list of timetable days: Monday–Saturday
by default, each with a stable `day_code` and an `is_active` flag).

## Why this table, next

Stage 94 queued `school_days_v2` and `schedule_templates` as the two leaf
dependencies that unblock `schedule_slots` and the rest of the `timetable_*_v2`
family. `school_days_v2` goes first because its only foreign key points at
`schools`, which is already ported. `schedule_templates` (FKs to `schools`,
`sessions`, `terms`, all ported) is the natural Migration 167, after which
`schedule_slots` has no unported parents left.

## What the migration does

Preserves all 10 effective columns: `id`, `tenant_id`, `school_id`, `day_name`,
`day_code`, `day_order`, `is_active`, `client_uuid`, `updated_at`,
`is_deleted`. Note that the SQLite `CREATE TABLE` in `db.py` declares only the
first seven; `client_uuid`, `updated_at` and `is_deleted` are added later by
`_make_syncable()`. The effective-schema snapshot is the source of truth for
this series, so the PostgreSQL table includes them.

- `school_id` stays `INTEGER` to match `schools.id` (same as migration 134);
  the migration refuses to run if `schools.id` is not `INTEGER`.
- `day_order` and the 0/1 flags (`is_active`, `is_deleted`) map to `BIGINT`,
  the house conversion used throughout this series.
- `UNIQUE (tenant_id, school_id, day_code)` is kept as the named constraint
  `uq_school_days_v2_tenant_school_day_code`; the verification step checks the
  column set *and order*.
- `FOREIGN KEY (school_id) REFERENCES schools(id)` is kept as
  `fk_school_days_v2_school`, with no cascade, matching the source's
  `NO ACTION`.
- The partial unique index `idx_school_days_v2_client_uuid` (`WHERE client_uuid
  IS NOT NULL`) is recreated and verified.
- The SQLite `trg_school_days_v2_sync_defaults` (client UUID and `updated_at`
  defaults on insert) and `trg_school_days_v2_sync_touch` (monotonic
  `updated_at` bump on update) are recreated as `BEFORE` triggers sharing one
  function, `sync_school_days_v2_fields()`, following migration 134. The
  verification step asserts the trigger set is exactly those two.

The default Monday–Saturday rows that the SQLite application seeds for each
school are application data, not schema, and are not created by this migration.

## Registry and tests

Migration 166 is registered after migration 165. The registry assertions in
the 61 existing `tests/postgres/test_postgres_migration_*.py` files were
advanced the same mechanical way as in previous stages (`range(100, 166)` →
`range(100, 167)`, and each `POSTGRES_MIGRATIONS[-k]` position shifted by one).
`tests/postgres/test_stage80_table_gap_report.py` now expects 91 of 113 tables
covered and 22 unresolved (296 columns, 32 foreign keys, 36 indexes).
`POSTGRES_TABLE_GAP_DETAILS_STAGE95.{md,json}` regenerate the gap report.

Ten new checks are in
`tests/postgres/test_postgres_migration_166_school_days_v2.py`, covering the
registry position, the preserved DDL, execution of every statement, and a
rejection test for each verification step (wrong `schools.id` type, columns,
foreign key, unique constraint including column order, indexes, non-partial
client UUID index, triggers).

## Verification

- PostgreSQL-focused suite: **513 passed** (503 before this stage + 10 new).
  pytest was not installable in the build environment (no network), so the
  suite was run with a small local stand-in that implements the pytest features
  these tests use (`raises`, `parametrize`, `tmp_path`, `monkeypatch`) plus
  `unittest` classes. Please re-run with real `pytest tests/postgres` on your
  side to confirm.
- Python compilation: passed (whole package).
- Migration registry: **67 migrations**, versions **100–166**.
- Explicit PostgreSQL table definitions: **91 of 113**.
- Remaining table candidates: **22**.

The full application regression suite (including Playwright rendering tests)
was not re-run; this stage touches only `postgres_migration_*.py` files, the
registry, the PostgreSQL-focused tests and documentation.

SQLite startup, SQLite migrations, IndexedDB offline storage, and offline
synchronization are not modified. No live PostgreSQL server is available here,
so the DDL, the trigger function, and the validation queries have **not** been
executed against a real PostgreSQL instance. That remains the largest open risk
for the whole 100–166 series.

## Queued next

1. Migration 167: `schedule_templates` (13 columns, FKs to `schools`,
   `sessions`, `terms`; same sync columns/index/triggers pattern).
2. Then `schedule_slots`, which references `school_days_v2` and
   `schedule_templates`, followed by `teacher_availability_v2` and the other
   `timetable_*_v2` tables that reference it.
3. `staff_documents` and the `sync_*` group have no unported parents and can be
   done in any order. `sync_conflicts`, `sync_log` and `sync_tombstones` also
   have tenant/tombstone helper triggers in `postgres_tenant_triggers.sql` and
   `postgres_tombstone_triggers.sql` that need to be decided on together.
4. `schema_steps` is SQLite's own migration-bookkeeping table and probably
   should not be ported; confirm that before skipping it.
