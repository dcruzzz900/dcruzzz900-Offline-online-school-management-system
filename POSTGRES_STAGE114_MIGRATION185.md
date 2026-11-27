# Stage 114 — V142 — Migration 185: sync_log

Implemented a standalone PostgreSQL-native definition for the effective `sync_log` table,
which records each offline-sync push/pull (device, direction, entity, record/conflict/error
counts). It is written by `record_sync_log()` in `db.py`.

## Why this table, next

Stage 113 queued it first: no blockers (0 foreign keys), and `postgres_tenant_triggers.sql`
already defines a trigger on it that had no table to attach to.

## What the migration does

Preserves all 11 effective columns (10 from the source `CREATE TABLE` plus the nullable
`tenant_id TEXT` added by `migration_051`'s generic `direct=[...]` list, confirmed against
the effective schema snapshot): `id` BIGINT identity, `school_id INTEGER NOT NULL`,
`device_id TEXT NOT NULL`, `user_id INTEGER`, `direction TEXT NOT NULL`, `entity TEXT`,
`record_count` / `conflict_count` / `error_count` BIGINT DEFAULT 0, `created_at TEXT DEFAULT
CURRENT_TIMESTAMP`, `tenant_id TEXT`. Recreates the one non-unique index
`idx_sync_log_school (school_id, created_at)` (column order taken from `db.py`; the snapshot
records only the index name).

Verification checks column types, nullability **and defaults** (new in this series: the
counters must default to 0, `created_at` to CURRENT_TIMESTAMP, everything else to none).

Deliberately not added, because the source has none (verification asserts each is absent):
foreign keys, UNIQUE constraints, CHECK constraints. `direction` ('push'/'pull') is only a
comment in the source, not a CHECK.

## Trigger overlap

The tenant-stamp trigger `trg_sync_log_tenant_stamp_pg` already exists in
`postgres_tenant_triggers.sql` with the same condition and source column as SQLite, so this
migration relies on it (as migrations 182/183 did). Because that file may be applied before
or after this migration, verification accepts that single trigger being present or absent and
rejects any other.

## Registry and tests

Registered after migration 184. Registry assertions in the 80 earlier test files were
advanced mechanically (`range(100, 185)` -> `range(100, 186)`; each `POSTGRES_MIGRATIONS[-k]`
-> `[-(k+1)]`). Gap-report test now expects 110 of 113 covered, 3 unresolved (39 columns,
1 foreign key, 5 indexes). New tests: `tests/postgres/test_postgres_migration_185_sync_log.py`
(14 tests). `POSTGRES_TABLE_GAP_DETAILS_STAGE114.{md,json}` regenerate the report.

## Verification

- PostgreSQL-focused suite: 732 passed, 0 failed, using a stand-in runner because `pytest`
  could not be installed here (no network). 7 tests needing pytest's `tmp_path` /
  `monkeypatch` fixtures were not executed (`test_migration_tool_helpers.py`,
  `test_postgres_pool_config.py`); they do not touch this change. **Re-run with real
  `pytest` before merging**; expected total 739.
- Migration registry: 86 migrations, versions 100-185.
- Explicit PostgreSQL table definitions: 110 of 113; remaining: 3
  (`schema_steps`, `sync_changes`, `sync_conflicts`).

Nothing here has been executed against a live PostgreSQL server (in particular, the
`CURRENT_TIMESTAMP` default on a TEXT column and the default-string matching in verification
should be confirmed on a real server); the full application regression suite was not re-run;
SQLite startup, SQLite migrations and offline sync are unchanged.

## Queued next

1. `sync_changes` (17 columns, 0 FKs, 2 indexes) -- no blockers; no PostgreSQL references yet.
2. `sync_conflicts` (20 columns, 1 FK to `schools.id`) -- not blocked by the others;
   `postgres_tenant_triggers.sql` already references it and the source adds `tenant_id`.
3. `schema_steps` -- SQLite's own migration bookkeeping; recommendation unchanged (do not
   port), but the decision should be recorded explicitly so coverage can be declared complete.
