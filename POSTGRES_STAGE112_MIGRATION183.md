# Stage 112 — V140 — Migration 183: timetable_entries

Implemented a standalone PostgreSQL-native definition for the effective `timetable_entries`
table: one timetable slot per class/day/period, with its subject, teacher and room. This is
the second and last of the two original (`migration_038`) timetable tables -- its sibling
and one of its own foreign-key parents, `timetable_periods`, was ported in migration 182.

## Why this table, next

Stage 111 named it directly as the next queued item (it only had one real blocker,
`timetable_periods`, which migration 182 just supplied), and it is the only remaining
unported table with any foreign keys at all -- every other table left in the gap report
(the `sync_*` group and `schema_steps`) has at most one FK, all newly relevant only once
this one was out of the way.

## Same approach as migration 182, confirmed independently

Like `timetable_periods`, the source has 12 effective columns, not the 11
`migration_038_timetable()` alone shows: `migration_051_registration_security_spec()`'s
generic `direct=[...]` table list adds a 12th, nullable `tenant_id TEXT`, backfilled from
`schools.tenant_id` via `school_id`. This round checked that directly against the effective
schema snapshot rather than assuming it from the migration-182 precedent. `postgres_tenant_
triggers.sql`'s `app_stamp_tenant_timetable_entries()` and `postgres_tombstone_triggers.sql`'s
`trg_timetable_entries_tombstone` are both correct for this table on the same grounds
migration 182 verified for `timetable_periods` (same condition, same source columns), so
this migration relies on them rather than re-implementing tenant-stamp or tombstone logic --
the same answer to Stage 110's "decide the trigger-overlap question" item, now given for
both of the two tables it named.

## What the migration does

Preserves all 12 effective columns, all 5 foreign keys, and both constraint-bearing
indexes. Full DDL and verification are in `postgres_migration_183_timetable_entries.py`.

- Five foreign keys: `school_id` -> `schools.id`, `class_id` -> `classes.id`, `period_id`
  -> `timetable_periods.id`, `subject_id` -> `subjects.id`, `teacher_id` -> `users.id`.
  Key types follow the parents: `school_id`/`class_id`/`subject_id`/`teacher_id` stay
  INTEGER (`schools.id`, `classes.id`, `subjects.id` and `users.id` are all INTEGER in
  `postgres_schema_base.sql`); `period_id` is BIGINT, matching migration 182's BIGINT
  identity `timetable_periods.id`.
- `idx_timetable_entries_slot`, the UNIQUE `(class_id, day_of_week, period_id)`
  one-slot-per-class/day/period rule -- a plain `CREATE UNIQUE INDEX` in the source, not a
  table-level UNIQUE constraint, recreated the same way (verification checks there is no
  table-level UNIQUE constraint at all).
- `idx_timetable_entries_teacher`, the non-unique `(teacher_id, day_of_week)` lookup index.
- The usual partial unique client-UUID index and client_uuid/updated_at sync-default/touch
  triggers, same pattern as migration 182 and the rest of this series.
- No tenant-stamp or tombstone trigger created here (see above).
- No CHECK constraints in the source; verification asserts none exist.

## Registry and tests

Registered after migration 182. Registry assertions in the 78 earlier migration test files
were advanced mechanically (`range(100, 183)` -> `range(100, 184)`; each
`POSTGRES_MIGRATIONS[-k]` shifted by one). The gap-report test now expects
108 of 113 tables covered and 5 unresolved (55 columns,
1 foreign key, 7 indexes) -- exactly the `sync_*` group and `schema_steps`. New tests:
`tests/postgres/test_postgres_migration_183_timetable_entries.py` (13 tests).
`POSTGRES_TABLE_GAP_DETAILS_STAGE112.{md,json}` regenerate the report.

## Verification

- PostgreSQL-focused suite: **714 passed** (701 before + 13 new), run directly with the
  real `pytest`.
- Migration registry: **84 migrations**, versions **100-183**.
- Explicit PostgreSQL table definitions: **108 of 113**; remaining: **5**
  (`schema_steps`, `sync_changes`, `sync_conflicts`, `sync_log`, `sync_tombstones`).
- `py_compile` clean on the new migration file and the updated registry.

Nothing here has been executed against a live PostgreSQL server; the full application
regression suite was not re-run; SQLite startup, SQLite migrations and offline sync are
unchanged.

## Queued next

1. **The `sync_*` group** is now the entire remaining candidate list apart from
   `schema_steps`. `sync_tombstones` (5 columns, 0 FKs, 1 index) is the one with no
   blockers and the most reason to go first: every tombstone trigger this track now relies
   on for three tables (`timetable_rooms_v2` and others covered by
   `postgres_tombstone_triggers.sql` in earlier stages, plus `timetable_periods` and
   `timetable_entries` from this and the prior stage) inserts into it, and nothing has
   created it in PostgreSQL yet. `sync_log` (11 columns, 0 FKs) has no blockers either.
   `sync_conflicts` (20 columns, 1 FK) should come after whichever of the two others its
   FK points at (not yet checked which).
2. `schema_steps` is SQLite's own migration bookkeeping and probably should not be ported
   (unchanged recommendation since Stage 94).
3. Once the `sync_*` group and the `schema_steps` decision are settled, table-level
   coverage in this report reaches its ceiling (every source table either explicitly
   created or deliberately excluded) -- the next horizon after that is the deeper,
   not-yet-started work this report has flagged every stage as out of scope: column/type/
   default/identity parity across all tables, full FK/index parity, and SQLite trigger
   conversion, none of which this file-presence report can check.
