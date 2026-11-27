# Stage 113 — V141 — Migration 184: sync_tombstones

Implemented a standalone PostgreSQL-native definition for the effective `sync_tombstones`
table, which records hard deletions so offline devices can drop the matching records on
their next pull.

## Why this table, next

Stage 112 queued it first: it has no blockers (0 foreign keys), and every
`trg_<table>_tombstone` function in `postgres_tombstone_triggers.sql` inserts into it while
nothing had created it in PostgreSQL. Until this migration, any DELETE on a tombstoned
table would have failed once those triggers were applied.

## What the migration does

Preserves all 5 effective columns (confirmed against `postgres_effective_schema_snapshot.json`):
`id` (BIGINT identity, as elsewhere in this series for AUTOINCREMENT keys), nullable
`school_id INTEGER`, and NOT NULL `entity`, `client_uuid`, `deleted_at` (UTC text).
Recreates the one index, the non-unique `idx_sync_tombstones_school (school_id, deleted_at)`.

Deliberately **not** added, because the source has none of them (verification asserts each
is absent): foreign keys (a tombstone must outlive its school row; the trigger functions
already yield NULL for a missing parent), UNIQUE constraints or a unique `client_uuid` index
(one record can be deleted, recreated and deleted again), CHECK constraints, tenant_id /
updated_at / is_deleted columns, and triggers on the table itself.

## Registry and tests

Registered after migration 183. Registry assertions in the 79 earlier test files were
advanced mechanically (`range(100, 184)` -> `range(100, 185)`; each
`POSTGRES_MIGRATIONS[-k]` -> `[-(k+1)]`). The gap-report test now expects 109 of 113 tables
covered and 4 unresolved (50 columns, 1 foreign key, 6 indexes). New tests:
`tests/postgres/test_postgres_migration_184_sync_tombstones.py` (11 tests).
`POSTGRES_TABLE_GAP_DETAILS_STAGE113.{md,json}` regenerate the report.

## Verification

- PostgreSQL-focused suite: 718 passed, 0 failed using a stand-in runner, because
  `pytest` could not be installed in this environment (no network). 7 tests that need
  pytest's `tmp_path`/`monkeypatch` fixtures (`test_migration_tool_helpers.py`,
  `test_postgres_pool_config.py`) were not executed here and do not touch this change.
  **Re-run with real `pytest` before merging**; expected total 725.
- Migration registry: 85 migrations, versions 100-184.
- Explicit PostgreSQL table definitions: 109 of 113; remaining: 4
  (`schema_steps`, `sync_changes`, `sync_conflicts`, `sync_log`).

Nothing here has been executed against a live PostgreSQL server; the full application
regression suite was not re-run; SQLite startup, SQLite migrations and offline sync are
unchanged.

## Queued next

1. `sync_log` (11 columns, 0 FKs, 1 index) -- no blockers; `postgres_tenant_triggers.sql`
   already references it.
2. `sync_changes` (17 columns, 0 FKs, 2 indexes) -- no PostgreSQL references found yet.
3. `sync_conflicts` (20 columns, 1 FK) -- checked this stage: its only FK is
   `school_id` -> `schools.id`, so it is not blocked by `sync_log` or `sync_changes` and the
   three can be ported in any order.
4. `schema_steps` is SQLite's own migration bookkeeping; recommendation unchanged: do not
   port, but record that decision explicitly.
