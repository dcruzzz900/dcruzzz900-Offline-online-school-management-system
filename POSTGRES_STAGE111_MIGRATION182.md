# Stage 111 — V140 — Migration 182: timetable_periods

Implemented a standalone PostgreSQL-native definition for the effective `timetable_periods`
table: named timetable periods (with optional start/end times, a sort order and a break
flag), shared school-wide. This is one of the two original (`migration_038`) timetable
tables, predating the `_v2` family ported across migrations 166-180.

## Correction found while scoping this table

Austin's zip arrived with no new message, so per the established pattern this round picked
the next queued item from Stage 110's own notes (`timetable_periods`, then `timetable_entries`)
and first had to settle Stage 110's open question about the trigger-overlap scripts for
these two tables.

A first read of `migration_038_timetable()` in isolation suggested `timetable_periods` has
no `tenant_id` at all, unlike the `_v2` tables — and an early draft of this migration and
these notes said so, and called `postgres_tenant_triggers.sql`'s
`app_stamp_tenant_timetable_periods()` trigger a bug (referencing a column that didn't
exist). That was wrong, caught before packaging by checking the actual effective schema
snapshot rather than trusting a single grep: the real table has 11 columns, not 10. A
later migration, `migration_051_registration_security_spec()`, adds `tenant_id TEXT` to
`timetable_periods` (and `timetable_entries`) through its generic `direct=[...]` table
list — nullable, backfilled once from `schools.tenant_id` via `school_id`, and kept
populated afterwards by a SQLite `AFTER INSERT` trigger
(`trg_timetable_periods_tenant_stamp`) that only fills it when NULL/empty. Checked against
that real behavior, `postgres_tenant_triggers.sql`'s existing
`app_stamp_tenant_timetable_periods()` / `trg_timetable_periods_tenant_stamp_pg` (a
`BEFORE INSERT` equivalent, same condition, same source column) is correct, and so is
`postgres_tombstone_triggers.sql`'s existing `trg_timetable_periods_tombstone` (keyed off
`OLD.school_id` / `OLD.client_uuid`, both present via `_make_syncable()`).

## Decision this answers from Stage 110

For `timetable_periods` (and, next stage, `timetable_entries`), rely on those two
dedicated, already-correct scripts for the tenant-stamp and tombstone triggers rather than
re-implementing them inside the numbered migration. This migration therefore creates only
the table, its two indexes, and the generic client_uuid/updated_at sync-default/touch
triggers (same pattern migration 166 established) — it does not add a tenant-stamp or
tombstone trigger itself, so there is nothing to conflict with those two scripts if they
are ever applied. This is a different answer than the one given implicitly for the 15
`_v2` tables in migrations 166-180, where the per-table sync-timestamp trigger pair
*is* duplicated against the generic `postgres_sync_timestamp_triggers.sql` (overlap
recorded, not resolved, in Stage 110) — that overlap is left exactly as Stage 110 found
it; this stage only resolves the question for the two tables it actually touches.

## What the migration does

Preserves all 11 effective columns, the single foreign key (`school_id` -> `schools.id`),
and both indexes. Full DDL and verification are in
`postgres_migration_182_timetable_periods.py`.

- `tenant_id` is `TEXT`, nullable, no foreign key — matching the source exactly (not
  `NOT NULL` like the `_v2` tables' `tenant_id`, which the application always supplies
  itself at insert).
- `idx_timetable_periods_school` on `(school_id, sort_order)`, non-unique, recreated.
- `idx_timetable_periods_client_uuid`, the usual partial unique index on `client_uuid`.
- `sort_order` and `is_break` map to BIGINT, matching house style for SQLite INTEGER
  columns with numeric defaults.
- No UNIQUE or CHECK constraints in the source; verification asserts there are none.
- Exactly two triggers created by this migration: `trg_timetable_periods_sync_defaults`
  and `trg_timetable_periods_sync_touch`. No tenant-stamp or tombstone trigger (see above).

## Registry and tests

Registered after migration 181. Registry assertions in the 77 earlier migration test files
were advanced mechanically (`range(100, 182)` -> `range(100, 183)`; each
`POSTGRES_MIGRATIONS[-k]` shifted by one). The gap-report test now expects
107 of 113 tables covered and 6 unresolved (67 columns,
6 foreign keys, 10 indexes). New tests:
`tests/postgres/test_postgres_migration_182_timetable_periods.py` (12 tests).
`POSTGRES_TABLE_GAP_DETAILS_STAGE111.{md,json}` regenerate the report.

## Verification

- PostgreSQL-focused suite: **701 passed** (689 before + 12 new), run directly with the
  real `pytest` (importable in this sandbox, confirming Stage 93's note that it is).
- Migration registry: **83 migrations**, versions **100-182**.
- Explicit PostgreSQL table definitions: **107 of 113**; remaining: **6**.
- `py_compile` clean on the new migration file and the updated registry.

Nothing here has been executed against a live PostgreSQL server; the full application
regression suite was not re-run; SQLite startup, SQLite migrations and offline sync are
unchanged.

## Queued next

1. `timetable_entries` — the other legacy timetable table, now the only remaining
   candidate with a foreign key (5 FKs: `school_id`, `class_id`, `period_id` ->
   `timetable_periods.id`, `subject_id`, `teacher_id`) and 3 indexes, including the
   UNIQUE `(class_id, day_of_week, period_id)` slot constraint. It also has `tenant_id`
   via the same `migration_051` mechanism, and the same already-correct tenant-stamp and
   tombstone scripts apply — same approach as this stage.
2. The `sync_*` group (`sync_changes`, `sync_conflicts`, `sync_log`, `sync_tombstones`) —
   `sync_tombstones` in particular is a real dependency of every tombstone trigger
   (including the ones this stage is relying on for `timetable_periods`): those triggers
   insert into it, but nothing has created it in PostgreSQL yet. Worth doing early in the
   next stage or two, not left indefinitely.
3. `schema_steps` is SQLite's own migration bookkeeping and probably should not be ported
   (unchanged recommendation from Stage 94).
