# Stage 115 — V143 — Migration 186: sync_changes

Implemented a standalone PostgreSQL-native definition for the effective `sync_changes` table:
one row per change a device replayed from its offline queue (`offline_sync.py`), which makes a
retried push idempotent.

## Why this table, next

Stage 114 queued it first: no foreign keys and no blockers, and it was the largest remaining
table-level gap after `sync_log` (17 columns).

## What the migration does

Preserves all 17 effective columns (confirmed against the effective schema snapshot;
`tenant_id` is declared directly in the source `CREATE TABLE`, so there is no later-added
column and no tenant-stamp trigger is needed). Defaults preserved: `received_at TEXT DEFAULT
CURRENT_TIMESTAMP`, `state TEXT NOT NULL DEFAULT 'applied'`, `attempts BIGINT DEFAULT 1`.
`id` is a BIGINT identity; `status_code` / `attempts` BIGINT; `school_id` / `user_id` INTEGER.

**Unlike `sync_tombstones` and `sync_log`, this table has a real constraint:**
`UNIQUE(school_id, change_id)`, which `offline_sync.py` relies on for
`INSERT ... ON CONFLICT(school_id, change_id) DO UPDATE` upserts. It is recreated as a *named
table-level UNIQUE constraint* (`sync_changes_school_id_change_id_key`), not a bare index, and
verification checks exactly one UNIQUE constraint with columns `(school_id, change_id)` in that
order. The non-unique `idx_sync_changes_school (school_id, received_at)` is also recreated.

Deliberately not added (source has none; verification asserts each is absent): foreign keys,
CHECK constraints (the `applied | conflict | failed` list on `state` is only a comment), and
triggers.

## Registry and tests

Registered after migration 185. Registry assertions in the 81 earlier test files advanced
mechanically (`range(100, 186)` -> `range(100, 187)`; each `POSTGRES_MIGRATIONS[-k]` ->
`[-(k+1)]`). Gap-report test now expects 111 of 113 covered, 2 unresolved (22 columns, 1
foreign key, 3 indexes). New tests:
`tests/postgres/test_postgres_migration_186_sync_changes.py` (15 tests, including wrong column
order / missing / extra UNIQUE constraint, and wrong defaults).
`POSTGRES_TABLE_GAP_DETAILS_STAGE115.{md,json}` regenerate the report.

## Verification

- PostgreSQL-focused suite: 747 passed, 0 failed, using a stand-in runner because `pytest`
  could not be installed here (no network). 7 tests needing pytest's `tmp_path` /
  `monkeypatch` fixtures were not executed (`test_migration_tool_helpers.py`,
  `test_postgres_pool_config.py`); they do not touch this change. **Re-run with real
  `pytest` before merging**; expected total 754.
- Migration registry: 87 migrations, versions 100-186.
- Explicit PostgreSQL table definitions: 111 of 113; remaining: 2
  (`schema_steps`, `sync_conflicts`).

Nothing here has been executed against a live PostgreSQL server (in particular, confirm on a
real server that `ON CONFLICT (school_id, change_id)` resolves against the named UNIQUE
constraint and that the `'applied'::text` default string matches in verification); the full
application regression suite was not re-run; SQLite startup, SQLite migrations and offline
sync are unchanged.

## Queued next

1. `sync_conflicts` (20 columns, 1 FK `school_id` -> `schools.id`, 2 indexes) -- the last real
   table. `postgres_tenant_triggers.sql` already defines `app_stamp_tenant_sync_conflicts` /
   `trg_sync_conflicts_tenant_stamp_pg` and the source adds `tenant_id` via `migration_051`,
   so follow the `sync_log` approach (rely on, and tolerate, the existing tenant trigger).
2. `schema_steps` -- SQLite's own migration bookkeeping (2 columns, 1 index); recommendation
   unchanged: do not port. Record the decision explicitly (and teach the gap report about
   deliberate exclusions) so table-level coverage can be declared complete.
3. After that: the deeper parity work every gap report has flagged as out of scope (column /
   type / default / identity parity across all tables, full FK / index parity, SQLite trigger
   conversion) and, most importantly, running the whole migration series against a live
   PostgreSQL server, which has still never been done.
