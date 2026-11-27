# Stage 117 — V145 — `schema_steps` exclusion; table-level coverage complete

No new migration this stage (registry unchanged: 88 migrations, versions 100-187).

## The decision

`schema_steps` (2 columns, 1 index) is **deliberately not ported**. Verified from the code, not
assumed: every read and write of it is in `db.py`'s SQLite migration runner (named-step
bookkeeping, `INSERT OR IGNORE INTO schema_steps`, the `sqlite_master` probe), plus one count
in `tools/build_postgres_effective_schema_snapshot.py`. The PostgreSQL runner
(`postgres_migrations.py`) keeps its own `app_schema_migrations` table with a per-migration
checksum, so a ported `schema_steps` would duplicate, and could disagree with, that record.

## What changed

- `tools/reconcile_postgres_table_details.py` gains `EXCLUDED_TABLES` (table -> reason).
  Excluded tables are reported in their own section and counted separately from unresolved ones,
  so "deliberately excluded" is distinguishable from "not yet done".
- The report **fails closed**: `build()` raises if an excluded name is not in the effective
  schema (stale entry) or if an excluded table later gains an explicit PostgreSQL
  `CREATE TABLE` (so an exclusion cannot silently hide a real gap).
- The rendered report states completion without overclaiming: it says explicitly that this is
  still not a live-catalog result.
- `tests/postgres/test_stage80_table_gap_report.py` rewritten: 3 tests -> 8 (coverage totals,
  ported + excluded + unresolved == source tables, `schema_steps` excluded with a reason, both
  fail-closed paths, rendered wording, live catalog not claimed).
- `POSTGRES_TABLE_GAP_DETAILS_STAGE117.{md,json}` regenerate the report.

## Result

| | Tables |
|---|---:|
| Source tables | 113 |
| Explicit PostgreSQL `CREATE TABLE` | 112 |
| Deliberately excluded (`schema_steps`) | 1 |
| Unresolved | 0 |

## Verification

- PostgreSQL-focused suite: 766 passed, 0 failed, using a stand-in runner because `pytest`
  could not be installed here (no network). 7 tests needing pytest's `tmp_path` / `monkeypatch`
  fixtures were not executed (`test_migration_tool_helpers.py`, `test_postgres_pool_config.py`);
  they do not touch this change. **Re-run with real `pytest` before merging**; expected total 773.
- No PostgreSQL server or driver is available in this environment, so nothing has been run
  against a live database. This remains the single largest unverified risk.

## What "complete" does and does not mean

Table-level coverage is complete **at the file level only**: each source table has an explicit
`CREATE TABLE` statement in a migration file (or is excluded with a reason). It does not mean the
series has run on PostgreSQL, nor that types, defaults, constraints, indexes, identity columns or
the 158 SQLite triggers are at parity.

## Queued next

1. **Run migrations 100-187 on a scratch PostgreSQL database** (real server, empty schema,
   `psycopg` per `requirements-postgres.txt`) and fix whatever fails. Check first:
   `CURRENT_TIMESTAMP` defaults on TEXT columns and the default-string matching in verification
   (185-187); `ON CONFLICT (school_id, change_id)` against the named UNIQUE constraint (186);
   foreign-key ordering across the whole series; applying `postgres_tenant_triggers.sql` and
   `postgres_tombstone_triggers.sql` before and after the sync tables.
2. A catalog-based parity check (compare `information_schema` / `pg_catalog` of the migrated
   database with `postgres_effective_schema_snapshot.json`: columns, types, nullability,
   defaults, FKs, indexes), replacing the file-presence report as the source of truth.
3. SQLite trigger conversion and application query compatibility.
