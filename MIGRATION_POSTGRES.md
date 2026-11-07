# Moving to PostgreSQL - audit and plan

Why: SQLite is one file on one machine. PostgreSQL gives many app servers, real concurrent writers, replication/failover,
point-in-time backups - what 1,000+ schools / 1,000+ simultaneous users needs beyond one big server (see SCALING.md).

## Status
NOT started in code. This build environment has no PostgreSQL server, driver or network, so nothing PostgreSQL-specific can
be executed or verified here, and a blind port of ~1,800 SQL statements would be unsafe for a live system.
What exists: the audit below (`python tools/pg_compat_audit.py --list`), `docker-compose.postgres.yml`, and the load test
(tests/load) to re-measure after the move.

## Audit: SQL that will not run unchanged (code base is SQLite-only today)
| Item | Count | Fix |
|---|---|---|
| `?` placeholders | 835 | mechanical: driver layer converts to `%s` |
| `execute()` calls in total | 1,771 | all go through one new database layer |
| `AUTOINCREMENT` / `rowid` (schema) | 121 | `GENERATED ... AS IDENTITY` |
| `CREATE TRIGGER` (sqlite syntax) | 38 | rewrite as PL/pgSQL functions + triggers (or app logic) |
| `.lastrowid` | 36 | `INSERT ... RETURNING id` |
| `datetime('now')` / `strftime` | 36 | `now()` / `to_char` |
| `INSERT OR IGNORE / REPLACE` | 29 | `ON CONFLICT (...) DO NOTHING/UPDATE` - needs each table's key |
| `sqlite_master` / `table_info` (migrations) | 24 | `information_schema` |
| `PRAGMA` | 15 | remove / `SET` equivalents |
| table rebuilds / renames in migrations | 7 | native `ALTER TABLE` |
| `GROUP BY` with non-aggregated columns | 41 | PostgreSQL rejects these: rewrite each query by hand |
| `LIKE` (case-insensitive in SQLite only) | 35 | `ILIKE` where intended |
| `tenant_id` TEXT compared with integer ids | 74 | unify the column types (PostgreSQL will not coerce) |

## Plan (each phase ends with ALL scenario suites green against the target database)
1. Database layer: one module (`dbapi`) exposing today's connection/cursor API (`execute`, `fetchone`, row access by name,
   `executemany`, transactions). SQLite backend unchanged -> existing suites stay green. PostgreSQL backend (psycopg 3 +
   connection pool, pgbouncer-friendly) with the mechanical translations above. Selected by `DATABASE_URL`.
2. PostgreSQL schema: ~122 tables generated from schema.sql/db.py, identity columns, trigger functions, proper types
   (decide TEXT vs INTEGER for tenant_id once), indexes reviewed for school/term-scoped queries.
3. Migration framework made dialect-aware (introspection + ALTER), so new schools/features migrate on both.
4. Manual review: the 41 GROUP BY queries, 74 tenant_id comparisons, 35 LIKE sites, upsert keys.
5. Data copy tool SQLite -> PostgreSQL (per school, row counts + checksums verified), dry-run, then cutover with a
   read-only window. Rollback = keep the SQLite file untouched.
6. Re-run tests/load against PostgreSQL on the target hardware; add Redis for rate limiting/sessions and a job queue for bulk PDFs.

## What is needed to do it properly
A place where PostgreSQL actually runs for development and CI (Docker on your machine, a cloud database, or a CI service) and
test output sent back for each phase. The phases are written so the existing suites are the acceptance test.
