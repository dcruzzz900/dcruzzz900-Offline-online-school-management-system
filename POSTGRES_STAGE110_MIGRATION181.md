# Stage 110 — V140 — Migration 181: staff_documents

Implemented a standalone PostgreSQL-native definition for the effective `staff_documents`
table: metadata of documents uploaded for staff members (original and stored file names,
MIME type, size, upload time). The files themselves are not stored in the database.

## Why this table, next

It has no foreign keys and no sync machinery, so nothing blocks it.

## What the migration does

Preserves all 10 effective columns. Full DDL and verification are in
`postgres_migration_181_staff_documents.py`.

- **Not part of offline sync.** The source has no `client_uuid`, `is_deleted` or sync
  triggers on this table, and none are added. The migration is therefore shorter than the
  recent timetable ones: table, one UNIQUE constraint, one index.
- **No foreign keys**, as in the source: `school_id` and `user_id` reference nothing. Both
  stay INTEGER to match `schools.id` and `users.id`.
- Composite UNIQUE `(user_id, stored_filename)` is the named constraint
  `uq_staff_documents_user_stored_filename`; verification checks the exact column set and
  order.
- Non-unique lookup index `idx_staff_documents_tenant_user` on `(tenant_id, school_id,
  user_id)` is recreated; verification checks it is non-unique and has those columns.
- `size_bytes` is BIGINT with default 0; `uploaded_at` and `updated_at` keep
  `TEXT DEFAULT CURRENT_TIMESTAMP`. Verification asserts there are no CHECK constraints
  and no triggers.

## Registry and tests

Registered after migration 180. Registry assertions in the 76 earlier migration test files
were advanced mechanically (`range(100, 181)` -> `range(100, 182)`; each
`POSTGRES_MIGRATIONS[-k]` shifted by one). The gap-report test now expects
106 of 113 tables covered and 7 unresolved (78 columns,
7 foreign keys, 12 indexes). New tests:
`tests/postgres/test_postgres_migration_181_staff_documents.py` (10 tests).
`POSTGRES_TABLE_GAP_DETAILS_STAGE110.{md,json}` regenerate the report.

## Verification

- PostgreSQL-focused suite: **689 passed** (679 before + 10 new), run with a local stand-in
  for pytest (no network to install it); please re-run `pytest tests/postgres`.
- Migration registry: **82 migrations**, versions **100-181**.
- Explicit PostgreSQL table definitions: **106 of 113**; remaining: **7**.

Nothing here has been executed against a live PostgreSQL server; the full application
regression suite was not re-run; SQLite startup, SQLite migrations and offline sync are unchanged.

## Finding: overlap with the helper trigger scripts (needs a decision)

`postgres_sync_timestamp_triggers.sql` (generated in an earlier stage, not applied by any
Python code) installs one `BEFORE INSERT OR UPDATE` trigger named `trg_<table>_sync_timestamp`,
calling a shared function `app_sync_timestamp_defaults()`, on 36 tables. Migration 134 and
migrations 166-180 instead create two per-table triggers (`_sync_defaults`, `_sync_touch`)
with a per-table function, following migration 134's pattern. 15 tables are covered by both
(`fixed_activities_v2`, `schedule_slots`, `schedule_templates`, `school_days_v2`,
`subject_room_requirements_v2`, `teacher_availability_v2`, `teacher_timetable_preferences_v2`,
`teacher_workload_profiles_v2`, `timetable_approvals_v2`, `timetable_audit_v2`,
`timetable_configurations_v2`, `timetable_conflicts_v2`, `timetable_rooms_v2`,
`timetable_types_v2`, `timetable_versions_v2`). If the script were applied after these
migrations, each of those tables would carry three timestamp triggers. From reading the two
function bodies, the extra trigger should be a no-op in practice (on insert both only fill
NULLs; on update the second sees `updated_at` already changed), but this has not been tested,
and one difference exists: the script's function raises an exception on a malformed
`updated_at` where the migration functions fall back silently. Options: (a) leave it and
treat the script as superseded for these tables; (b) make the script skip tables whose
migration already installs the triggers; (c) change the migrations to use the shared
function. This stage does not change anything; it records the overlap.

The same question applies to the tenant-stamp and tombstone scripts
(`postgres_tenant_triggers.sql`, `postgres_tombstone_triggers.sql`), which already define
PostgreSQL equivalents for `timetable_periods` and `timetable_entries`. Those two legacy
tables are the next candidates; the likely approach is to rely on the scripts for the tenant
and tombstone triggers rather than duplicating them in the migrations, but that needs a
decision first.

## Queued next

1. Decide the trigger-overlap question above.
2. `timetable_periods`, then `timetable_entries` (legacy tables; periods has an extra
   `(school_id, sort_order)` index; entries has two further indexes including a UNIQUE
   `(class_id, day_of_week, period_id)`).
3. The `sync_*` group (`sync_changes`, `sync_conflicts`, `sync_log`, `sync_tombstones`).
4. `schema_steps` is SQLite's own migration bookkeeping and probably should not be ported.
