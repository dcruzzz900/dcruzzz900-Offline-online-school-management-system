# Stage 116 — V144 — Migration 187: sync_conflicts

Implemented a standalone PostgreSQL-native definition for the effective `sync_conflicts`
table: offline-sync conflicts (client payload vs server payload) and how/by whom each was
resolved. This is the last real table in the table-level gap report.

## Why this table, next

Stage 115 queued it first. Its single foreign key points at `schools` (checked in Stage 115),
so it was never blocked by the other sync tables, and `postgres_tenant_triggers.sql` already
defines a trigger on it that had no table to attach to.

## What the migration does

Preserves all 20 effective columns (11 from the original `CREATE TABLE` plus `tenant_id`,
`change_id`, `kind`, `sensitive`, `reason`, `entity_key`, `resolved_by`, `method`, `path`
added by later migrations; confirmed against the effective schema snapshot). `id` BIGINT
identity; `resolved` / `sensitive` BIGINT DEFAULT 0; `detected_at TEXT DEFAULT
CURRENT_TIMESTAMP`; `school_id INTEGER NOT NULL`; `client_payload` / `server_payload` NOT NULL.

- One foreign key, `school_id` -> `schools.id`, named `fk_sync_conflicts_school`. As in
  migration 183, `schools.id` is checked to be INTEGER **before any DDL runs** (a test asserts
  no CREATE TABLE is issued on a mismatch).
- Two non-unique indexes: `idx_sync_conflicts_school (school_id, resolved)` and
  `idx_sync_conflicts_change (school_id, change_id)`; the latter's columns come from `db.py`,
  since the snapshot records only the name. Verification checks column order on both.
- No UNIQUE or CHECK constraints (source has none; asserted absent).

## Trigger overlap

`trg_sync_conflicts_tenant_stamp_pg` already exists in `postgres_tenant_triggers.sql` with the
same condition and source column as SQLite, so it is relied on rather than re-implemented.
Verification accepts that one trigger being present or absent (the tenant file may be applied
before or after this migration) and rejects any other.

## Registry and tests

Registered after migration 186. Registry assertions in the 82 earlier test files advanced
mechanically (`range(100, 187)` -> `range(100, 188)`; each `POSTGRES_MIGRATIONS[-k]` ->
`[-(k+1)]`). Gap-report test now expects 112 of 113 covered, 1 unresolved (`schema_steps`:
2 columns, 0 foreign keys, 1 index). New tests:
`tests/postgres/test_postgres_migration_187_sync_conflicts.py` (14 tests).
`POSTGRES_TABLE_GAP_DETAILS_STAGE116.{md,json}` regenerate the report.

## Verification

- PostgreSQL-focused suite: 761 passed, 0 failed, using a stand-in runner because `pytest`
  could not be installed here (no network). 7 tests needing pytest's `tmp_path` /
  `monkeypatch` fixtures were not executed (`test_migration_tool_helpers.py`,
  `test_postgres_pool_config.py`); they do not touch this change. **Re-run with real
  `pytest` before merging**; expected total 768.
- Migration registry: 88 migrations, versions 100-187.
- Explicit PostgreSQL table definitions: 112 of 113; remaining: 1 (`schema_steps`).

Nothing here has been executed against a live PostgreSQL server; the full application
regression suite was not re-run; SQLite startup, SQLite migrations and offline sync are
unchanged.

## Queued next

1. **`schema_steps` decision.** It is SQLite's own migration bookkeeping (2 columns, 1 index)
   and should not be ported. Record that explicitly -- e.g. an `EXCLUDED_TABLES` entry with a
   reason in `tools/reconcile_postgres_table_details.py` -- so the report distinguishes
   "deliberately excluded" from "not yet done" and table-level coverage can be declared complete
   (112 ported + 1 excluded = 113).
2. **Run the whole series against a live PostgreSQL server.** All 88 migrations (100-187) have
   only ever been checked against fake connections. Items flagged for first-run attention:
   `CURRENT_TIMESTAMP` defaults on TEXT columns and the default-string matching in
   verification (migrations 185-187); `ON CONFLICT (school_id, change_id)` against the named
   UNIQUE constraint (186); application of `postgres_tenant_triggers.sql` and
   `postgres_tombstone_triggers.sql` before/after these tables.
3. The deeper parity work flagged by every gap report as out of scope: column/type/default/
   identity parity for all tables, full FK/index parity, SQLite trigger conversion,
   application query compatibility.
