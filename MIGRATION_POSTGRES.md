# Moving to PostgreSQL - audit and plan

Why: SQLite is one file on one machine. PostgreSQL gives many app servers, real concurrent writers, replication/failover,
point-in-time backups - what 1,000+ schools / 1,000+ simultaneous users needs beyond one big server (see SCALING.md).

## Status
A PostgreSQL pool foundation has been added, but the application still runs on SQLite by default. This environment has no PostgreSQL server, Docker executable, psycopg driver or psycopg_pool package, so no live PostgreSQL schema or data migration can be executed or verified here. The application must not be switched to PostgreSQL until the compatibility work and acceptance gates below pass.

## Audit: SQL that needs PostgreSQL compatibility work
The exact current static counts are recorded below in **Current static audit (re-run against the uploaded v113 source)**. The audit is available as `python tools/pg_compat_audit.py --list`. It is a prioritization tool: every result needs context-aware review rather than blind text replacement.

## Plan (each phase ends with ALL scenario suites green against the target database)
1. Database layer: one module (`dbapi`) exposing today's connection/cursor API (`execute`, `fetchone`, row access by name,
   `executemany`, transactions). SQLite backend unchanged -> existing suites stay green. PostgreSQL backend (psycopg 3 +
   connection pool, pgbouncer-friendly) with the mechanical translations above. Selected by an explicit deployment setting only after the compatibility suite is green.
2. PostgreSQL schema: ~122 tables generated from schema.sql/db.py, identity columns, trigger functions, proper types
   (decide TEXT vs INTEGER for tenant_id once), indexes reviewed for school/term-scoped queries.
3. Migration framework made dialect-aware (introspection + ALTER), so new schools/features migrate on both.
4. Manual review: the GROUP BY queries, tenant_id comparisons, LIKE sites, and upsert keys.
5. Data copy tool SQLite -> PostgreSQL (per school, row counts + checksums verified), dry-run, then cutover with a
   read-only window. Rollback = keep the SQLite file untouched.
6. Re-run tests/load against PostgreSQL on the target hardware; add Redis for rate limiting/sessions and a job queue for bulk PDFs.

## What is needed to do it properly
A place where PostgreSQL actually runs for development and CI (Docker on your machine, a cloud database, or a CI service) and
test output sent back for each phase. The phases are written so the existing suites are the acceptance test.

## Architecture decision (2026-11-25)

The target is a dual-database deployment model:

- PostgreSQL is the central online database for hosted/multi-school deployments.
- SQLite remains supported for standalone/local school installations.
- IndexedDB remains the browser offline queue/cache; it continues to synchronize through Flask routes.
- The React/HTML/CSS/JavaScript/Bootstrap interface is not part of the database migration.
- PostgreSQL connections use a process-level psycopg 3 connection pool. Pool limits must be sized across *all* Gunicorn workers, not per worker in isolation.

## Work completed in this migration pass

- Added `postgres_pool.py`, an optional lazy-loaded psycopg 3 pool foundation with dict rows, connection/timeout settings, a health check and explicit shutdown.
- Added `requirements-postgres.txt`; local SQLite installs do not need the PostgreSQL driver.
- Added `POSTGRES_ENV.example` with non-secret configuration examples.
- Added isolated configuration tests in `tests/postgres/test_postgres_pool_config.py`.
- Preserved the existing SQLite `db.get_db()` path without modification. PostgreSQL is intentionally **not yet wired into application startup**: enabling it before the SQL and migration work below is complete would break existing screens and background jobs.

## Current static audit (re-run against the uploaded v113 source)

`python tools/pg_compat_audit.py` currently reports 1,935 `.execute()` calls and these SQLite compatibility items:

| Item | Current count |
|---|---:|
| `?` placeholders | 944 |
| `.lastrowid` | 40 |
| `AUTOINCREMENT` / `rowid` | 127 |
| SQLite trigger definitions | 40 |
| PRAGMA statements | 16 |
| `sqlite_master` / `table_info` introspection | 25 |
| SQLite date/time functions | 46 |
| `INSERT OR IGNORE / REPLACE` | 29 |
| `LIKE` semantics requiring review | 41 |
| `GROUP BY` sites requiring review | 45 |
| `tenant_id` comparison risks | 74 |

These are static-review counts, not a claim that each occurrence is independently broken. The audit is a prioritization tool; each occurrence needs context-aware conversion and tests.

## Remaining gates before PostgreSQL can be enabled

1. Implement the dialect-aware DB-API compatibility layer and route all production database access through it.
2. Port the full schema and the ordered migration framework, including 40 trigger behaviors, schema introspection, row IDs and transactional semantics.
3. Resolve all tenant ID type inconsistencies and verify that every tenant-scoped query remains scoped.
4. Review each upsert conflict target, each `GROUP BY`, case-insensitive search, and date/time expression.
5. Build a tested SQLite-to-PostgreSQL transfer utility with dry-run mode, row counts, checksums, sequence resets and a resumable failure report.
6. Run the existing module/RBAC/offline scenario suites against both SQLite and a real PostgreSQL 16 instance, then run tenant-isolation and load tests.
7. Only then expose a deployment switch for PostgreSQL. Keep the source SQLite database read-only and intact through the rollback window.

## Stage 23: date and time compatibility (partial, targeted)

The following runtime SQL expressions were replaced without changing the SQLite backend:

- Role-assignment expiry migrations now compare `end_date` with a bound UTC ISO date rather than SQLite `date('now')`.
- The staff-attendance 30-day dashboard filter now uses a bound UTC cutoff date rather than SQLite `date('now','-30 day')`.
- The subscription-renewals report now calculates whole calendar days remaining in Python from the ISO date, rather than SQLite `julianday()`. Its eight output columns and ordering are retained.

`db_compat.py` now provides `utc_today_iso()`, `utc_date_days_ago_iso()` and `days_between_iso_dates()`. These helpers are database-driver independent, use UTC calendar dates for the former SQLite `now` expressions, and are covered by focused tests. This is a deliberately narrow conversion, not a claim that all 46 date/time audit candidates have been resolved. SQLite timestamp defaults and trigger expressions remain in the SQLite migration path and still require PostgreSQL-specific schema/trigger conversion.

Validation for this stage: Python compilation passed for the edited modules; `tests/postgres` passed (125 tests). No live PostgreSQL server or driver is available in this environment, so PostgreSQL execution remains unverified.

## Environment limitation

This work environment has no Docker executable, PostgreSQL server, `psycopg` driver or `psycopg_pool` package. Therefore no live PostgreSQL connection, schema execution, migration, data copy, or PostgreSQL integration test has been performed. The added pool module is infrastructure groundwork, not a production-ready database switch. Do not set the application to PostgreSQL until all remaining gates pass.

## Data transfer utility (added in the next migration pass)

`tools/migrate_sqlite_to_postgres.py` is a deliberately conservative data-copy tool for a **pre-created and already PostgreSQL-compatible target schema**. It does not create or convert the schema and is not a substitute for the outstanding dialect-aware migration work.

- Dry-run is the default; `--apply` is required to write.
- Reads the SQLite source in read-only mode.
- Refuses missing target tables/columns, non-empty target tables, and foreign-key cycles rather than disabling constraints.
- Copies in parent-before-child order in one PostgreSQL transaction.
- Compares per-table row counts and order-independent SHA-256 checksums before commit.
- Resets serial/identity sequences after copying.
- Does not delete, truncate, or modify the source SQLite file.

Example (first run is validation only):

```bash
export DATABASE_URL='postgresql://...'
python tools/migrate_sqlite_to_postgres.py --sqlite instance/school.db
# After schema review, backup, and maintenance window:
python tools/migrate_sqlite_to_postgres.py --sqlite instance/school.db --apply --report migration-report.json
```

**Important limitation:** SQLite affinity values and PostgreSQL target types must already be compatible. In particular, integer-backed SQLite booleans, timestamp/text conventions, JSON, and BLOB columns need explicit schema/data mapping review. A checksum mismatch or any insert error rolls back the entire PostgreSQL transaction. Do not run `--apply` against production until schema/type mappings and a real PostgreSQL rehearsal pass.

### Stage 3 — conservative SQL parameter compatibility

`postgres_compat.py` now contains a small SQL-aware qmark converter for the
application's SQLite-style positional parameters. It converts `?` markers to
psycopg 3 `%s` markers only outside SQL strings, quoted identifiers, comments,
and PostgreSQL dollar-quoted bodies. When parameters are supplied, it checks
that the number of converted markers matches the parameter count. Identifier
quoting is also provided for migration tooling.

This helper is intentionally **not** wired into `get_db()` yet. It is not a
complete SQLite-to-PostgreSQL SQL dialect translator: SQLite PRAGMAs,
`sqlite_master`, `executescript`, `lastrowid`, SQLite date functions, trigger
syntax, conflict clauses, and type differences still need dedicated handling.
Do not pass PostgreSQL JSON `?` operators through the qmark converter. The
next integration phase must inventory and explicitly adapt those SQL patterns
before PostgreSQL can be enabled for application traffic.

### Stage 4 — pooled DB-API adapter groundwork

Added `postgres_dbapi.py` with an opt-in adapter around a checked-out psycopg pool connection:

- `execute()` / `executemany()` translate positional qmark parameters using the Stage 3 lexer.
- Result rows support both `row["column"]` and `row[0]` access, matching patterns found in the current SQLite application.
- `commit()`, `rollback()`, `cursor()`, context-manager handling, and pooled connection return are exposed.
- `lastrowid` raises an explicit `NotImplementedError`; affected INSERT statements must be changed to `INSERT ... RETURNING id` and consume the returned row.
- `executescript()` raises an explicit `NotImplementedError`; PostgreSQL migrations must be split into reviewed statements.

`postgres_pool.py` now configures the hybrid row factory for pooled connections. The adapter is still not selected by `db.get_db()` and does not make the application PostgreSQL-compatible by itself. It does not translate SQLite DDL, PRAGMAs, `sqlite_master`, conflict clauses, date functions, triggers, or implicit row-ID behavior. Existing SQL call sites must be converted and tested before the adapter can be wired into production.

Stage 4 isolated tests use fake DB-API objects and verify parameter conversion, numeric/name row access, transaction handling, pool release, and explicit rejection of unsupported SQLite APIs. They do not replace integration tests against a real PostgreSQL instance.

### Stage 5 — preserve existing database exception handling

The production code contains existing handlers for `sqlite3.IntegrityError`,
`sqlite3.OperationalError`, and related exception classes. Psycopg raises its
own DB-API exception hierarchy, so those handlers would otherwise miss some
PostgreSQL constraint and connection failures. `postgres_dbapi.py` now maps
recognized psycopg 3 database exceptions to their corresponding `sqlite3`
exception classes at the adapter boundary for `execute()`, `executemany()`,
`commit()`, and `rollback()`.

The mapping is lazy: importing the adapter does not require psycopg until a
PostgreSQL operation raises an exception. Unknown exceptions are re-raised
unchanged. This preserves common existing exception paths but does not prove
that every SQLite-specific error assumption is portable; application-specific
handlers and transaction recovery still require real PostgreSQL tests.

Stage 5 tests use controlled fake exception classes to verify the mapping and
confirm that unknown exceptions are not rewritten. They are not a substitute
for exercising real psycopg errors from PostgreSQL constraints, locks, network
failures, or transaction-aborted states.

### Stage 6 — PostgreSQL-native schema catalog helpers

Added `postgres_schema.py` for the PostgreSQL migration runner's catalog
operations. It provides parameterized helpers for table existence, ordered
column names, column type/nullability/default metadata, and index existence
using `information_schema` and `pg_indexes`. It also provides a
transaction-scoped `pg_advisory_xact_lock` helper so multiple application
workers cannot run the same PostgreSQL schema migration concurrently. The
lock is released automatically when the migration transaction commits or
rolls back; callers must therefore keep that transaction open for the full
migration.

These functions are not yet substituted into `db.py`. That file's current
migration runner includes SQLite-only operations beyond catalog lookup,
including file-based backup/locking, `executescript`, table rebuilds, trigger
syntax, and SQLite PRAGMAs. A safe PostgreSQL migration runner must be designed
separately rather than routing those functions through superficially similar
catalog calls. Stage 6 tests use fake connections and validate SQL shape,
parameter binding, result handling, and advisory-lock key validation; they do
not prove behavior against a live PostgreSQL server.

### Stage 7 — versioned PostgreSQL migration runner

Added `postgres_migrations.py`, a deliberately separate runner for newly authored,
PostgreSQL-native migrations. Each migration has a positive version, name, apply
callback, and source text used to calculate a SHA-256 checksum. The runner:

- acquires the transaction-scoped advisory lock before inspecting migration state;
- creates `app_schema_migrations` if needed;
- applies pending migrations in ascending version order;
- records each applied version and checksum;
- skips an already-applied migration only when its checksum is unchanged;
- refuses a modified historical migration (a new version must be created instead);
- commits the batch on success and rolls back on any error.

This runner is not wired into `db.py` and does not translate or execute the existing
SQLite migration functions. It is a foundation for a separately reviewed PostgreSQL
schema history. The existing v113 schema (about 122 tables) and its migration history,
including trigger behavior and SQLite table rebuilds, still need explicit PostgreSQL
migration definitions and live verification. Tests for this stage use fake DB-API
connections; no real PostgreSQL server was available in this environment.

### Stage 8 — PostgreSQL baseline schema draft

Added `tools/build_postgres_base_schema.py` and generated `postgres_schema_base.sql` from the existing `schema.sql` baseline. The generator performs one deliberately narrow DDL conversion: SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` becomes PostgreSQL `INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY`. It preserves the baseline's foreign keys, unique constraints, CHECK constraints, indexes and partial-index predicates.

The generated draft currently contains **24 baseline tables and 23 identity columns**, matching the source file. The original SQLite `schema.sql` was also executed against an in-memory SQLite database and created 24 user tables successfully. The PostgreSQL output has only been statically inspected and tested for expected transformations; it has **not** been executed on PostgreSQL because this environment has no PostgreSQL server/driver.

**Scope warning:** this is not the complete v113 schema. It does not include the subsequent `db.py` migration sequence, dynamically created tables, triggers, tenant backfills, or data conversions. Do not apply it as a complete production schema and do not point the application at it. It is a baseline artifact for the next phase, where the ordered `db.py` migrations and trigger behaviours must be ported and tested.

Validation added in `tests/postgres/test_postgres_baseline_schema.py` checks identity conversion, preservation of constraints/partial indexes, rejection of unconverted SQLite features, and matching table/identity counts. Stage 8 isolated PostgreSQL groundwork suite: **45 tests passed**; Python compilation passed.

### Stage 9 — ordered legacy migration inventory (no automatic port)

Added `tools/build_postgres_migration_inventory.py` and generated
`postgres_migration_inventory.json`. The tool parses the actual `MIGRATIONS`
and `STEPS` registries in `db.py`, preserving their execution order and recording
function names, source line ranges, docstrings, and SQLite-specific constructs
that require manual PostgreSQL review. This avoids relying on migration function
names alone: the application has two distinct migration mechanisms, and named
steps include historical compatibility branches.

For the current uploaded v113 source, the inventory contains **23 numbered
migrations and 76 named steps (99 registered entries)**. The static scan marks
82 entries for review. Within those registered function bodies it identifies
occurrences of `ensure_column` (155), trigger DDL (36), SQLite date/time
functions (15), SQLite upsert syntax (16), rowid references (10), PRAGMA or
`table_info` (8), table rebuilds (3), `lastrowid` (2), `sqlite_master` (1), and
`executescript` (1). These are AST-scoped source-text pattern counts, not a
count of all SQL statements in the app and not proof that every occurrence is
invalid on PostgreSQL. In particular, trigger definitions must be reviewed for
their exact side effects and ordering before replacement with PostgreSQL
trigger functions.

The JSON inventory is a review aid only. It does **not** generate PostgreSQL
migration SQL, execute the SQLite migrations, or alter the production
`db.py` migration path. A PostgreSQL schema still requires explicit, reviewed
migration definitions for the full ordered history, including tenant backfills,
constraints, trigger functions, table rebuild semantics, and compatibility
branches. Unit tests verify registry extraction/order and inventory reporting;
there is still no live PostgreSQL integration environment in this workspace.

### Stage 10 — effective v113 schema snapshot from the real migration registry

Added `tools/build_postgres_effective_schema_snapshot.py`. It imports the app's
real `db.py`, runs `run_migrations()` against a fresh in-memory SQLite database,
and inventories the resulting schema. This avoids relying only on the initial
`schema.sql` baseline or on static regex scans of migration source.

The generated reference files are:

- `postgres_effective_schema_snapshot.json` — per-table column metadata,
  primary-key positions, defaults, nullability, foreign keys, indexes, and the
  SQL source for tables, indexes, views, and triggers.
- `POSTGRES_EFFECTIVE_SCHEMA.md` — readable table/object inventory and porting
  cautions.

Current generated snapshot: schema-version high-water mark 99, 76 named steps,
113 application tables, 1,569 columns, 125 foreign-key declarations, 148
explicit indexes, and 158 triggers. These counts describe the schema created
from an empty database by the current SQLite migration registry; they do not
include customer data and may differ from a long-lived installation with
historical drift or manual changes.

This is a **SQLite source-of-truth inventory**, not a PostgreSQL schema or a
claim that the migrations have been ported. SQLite trigger bodies, date
functions, type affinity, conflict clauses, and table-rebuild logic still need
reviewed PostgreSQL equivalents. The script intentionally does not execute any
PostgreSQL DDL or change the application's selected database.

## Stage 11 — trigger porting inventory

`tools/build_postgres_trigger_porting_plan.py` consumes the effective SQLite schema snapshot and emits `postgres_trigger_porting_plan.json` plus `POSTGRES_TRIGGER_PORTING_PLAN.md`. It inventories all 158 triggers, preserving each original SQLite trigger body and classifying its likely purpose (tenant stamping, offline-sync defaults/timestamps, tombstones, immutability, uniqueness, and history capture).

This is intentionally **not** an automatic SQL converter. SQLite trigger syntax and semantics differ from PostgreSQL PL/pgSQL. In particular, `RAISE(ABORT)`, same-row `AFTER UPDATE` patterns, `IS`/`IS NOT`, and tenant inference require manual implementation and PostgreSQL integration tests. Do not apply the inventory as SQL.

## Stage 12 — append-only / immutability trigger conversion

`tools/build_postgres_immutability_triggers.py` generates
`postgres_immutability_triggers.sql` from the Stage 11 trigger inventory.
It currently covers the 30 `immutability_guard` triggers only. The generator
uses a shared PL/pgSQL function and preserves each trigger's source error
message, event, `UPDATE OF` column restriction, and the reviewed `WHEN`
conditions. SQLite `IS` / `IS NOT` comparisons are mapped to PostgreSQL's
`IS NOT DISTINCT FROM` / `IS DISTINCT FROM` to preserve NULL-safe semantics.

The generator fails closed for unsupported condition syntax. The generated SQL
is an opt-in migration artifact and is not applied automatically. It must be
reviewed against the target schema and exercised on PostgreSQL before use.
Tenant propagation, offline-sync timestamps, tombstones, cross-row uniqueness,
and audit/history capture remain unported.

Regenerate with:

```bash
python tools/build_postgres_immutability_triggers.py
```

Validation currently includes unit tests for all 30 generated declarations and
condition translation. No live PostgreSQL server was available for execution
or trigger integration tests in this environment.

## Stage 13 — tenant propagation trigger port

- Inspected all 29 `tenant_scope_propagation` SQLite triggers and added a fail-closed PostgreSQL generator.
- Generated 28 PostgreSQL `BEFORE INSERT` triggers; the two overlapping `students` SQLite triggers are combined into one `NEW`-record assignment trigger.
- Preserved existing tenant values and explicitly mapped direct school, class, and student-to-class-to-school relationships.
- Added source-shape and effective-schema column checks, tests, and `POSTGRES_TENANT_TRIGGERS.md`.
- Generated SQL is not automatically applied. No live PostgreSQL runtime is available here; PostgreSQL execution and integration testing remain required.

## Stage 14 — offline-sync timestamp trigger port

- Inspected all 72 `offline_sync_timestamp` SQLite triggers across 36 tables.
- Added `tools/build_postgres_sync_timestamp_triggers.py` and generated
  `postgres_sync_timestamp_triggers.sql` with one PostgreSQL `BEFORE INSERT OR
  UPDATE` trigger per table. This replaces SQLite's same-row `AFTER` update
  pattern and avoids self-update recursion.
- Preserved the legacy 32-character lowercase hexadecimal `client_uuid`
  format, UTC seconds-resolution `updated_at` text format, caller-supplied
  values, unchanged-timestamp detection (including NULL-to-NULL), and the
  one-second monotonic fallback.
- The generator verifies all 72 source trigger shapes and confirms that all
  36 target tables have TEXT `client_uuid` and `updated_at` columns. It fails
  closed if the inventory or schema differs.
- Added `POSTGRES_SYNC_TIMESTAMP_TRIGGERS.md` and automated tests. The SQL is
  generated only; it is not automatically applied. No live PostgreSQL server
  or driver is available in this environment, so PostgreSQL execution and
  end-to-end offline push/pull/conflict tests remain required.

Regenerate with:

```bash
python tools/build_postgres_sync_timestamp_triggers.py
```

## Stage 15 — PostgreSQL sync tombstone triggers

- Ported all 18 SQLite `AFTER DELETE` tombstone triggers to one shared PostgreSQL PL/pgSQL trigger function plus 18 table-specific triggers.
- Preserved per-row behavior, the `client_uuid IS NOT NULL` guard, entity/table name, UUID, UTC seconds-resolution text timestamp, and same-transaction atomicity.
- Preserved all reviewed school-scope expressions: direct `OLD.school_id` and parent lookups through classes, students/classes, or sessions. Missing parent lookups continue to yield NULL, matching SQLite scalar-subquery behavior.
- Generator validates the exact 18-trigger inventory and effective schema and rejects unreviewed source shapes. SQL is generated but not applied automatically.
- Added `tools/build_postgres_tombstone_triggers.py`, `postgres_tombstone_triggers.sql`, `POSTGRES_TOMBSTONE_TRIGGERS.md`, and `tests/postgres/test_postgres_tombstone_triggers.py`.
- Validation: Python compilation passed; PostgreSQL migration test suite passed (74 tests).
- Limitation: no live PostgreSQL server/driver is available in this runtime. Run staging integration tests for cascaded deletes, NULL/non-NULL UUIDs, parent lookup behavior, multi-row deletes, rollback, and school-scoped sync pulls before production use.

## Stage 16 — cross-row uniqueness and identity guards

- Reviewed all 5 SQLite `cross_row_uniqueness` trigger definitions.
- Added `tools/build_postgres_uniqueness.py` and generated `postgres_uniqueness.sql`.
- Added four authoritative unique expression indexes for student admission numbers, usernames, emails and school-scoped staff IDs. These indexes, rather than trigger-side reads, enforce uniqueness safely under concurrent writes.
- Added trigger checks to retain legacy-friendly errors for ordinary conflicts and preserved the permanent `signup_name` guard.
- Added a preflight block that stops deployment when existing duplicate identities are found; it does not modify source data.
- Strengthened the users update trigger to include `school_id`, closing a bypass because staff-ID uniqueness is school-scoped.
- Added six generator tests. PostgreSQL SQL has not been executed against a live server; locale/collation behavior and production duplicate handling still require integration verification.

## Stage 17 — billing payment audit/history capture

- Reviewed and ported the two `billing_payments` history triggers.
- Added a single PL/pgSQL function and separate AFTER INSERT / AFTER UPDATE
  triggers in `postgres_audit_history.sql`.
- Preserved NULL-safe change detection, action classification, actor fallback,
  old/new snapshots, and same-transaction history writes.
- Preserved the source quirk that `provider` appears in UPDATE OF but is not
  part of the WHEN predicate, so provider-only updates do not emit history.
- Added a fail-closed generator and static regression tests. No live PostgreSQL
  server was available; generated SQL remains un-applied and requires target-DB
  integration verification.

## Stage 18 — remaining business-rule trigger port

- Reviewed the final two SQLite triggers classified as `business_rule_or_other`.
- Added `tools/build_postgres_business_rule_triggers.py` and generated
  `postgres_business_rule_triggers.sql` with two PL/pgSQL functions and two
  row-level triggers.
- Preserved permanent non-empty school IDs, NULL-aware comparison, and the
  original exception message. Preserved signup-name initialization as an
  `AFTER INSERT` same-transaction update, including NULL/empty handling.
- Added fail-closed source/schema validation, deployment notes, and regression
  tests. SQL is opt-in and not applied automatically.
- No live PostgreSQL server was available; validate exception mapping, trigger
  ordering, multi-row inserts, and rollback on a disposable PostgreSQL database.

## Stage 19 — application PostgreSQL remediation inventory

- Added `tools/build_postgres_remediation_inventory.py` to generate a machine-readable JSON inventory and a human-readable remediation queue from runtime Python modules only.
- The inventory records file, line, category, and a short source excerpt for each candidate. It excludes tests, migration generators, and utility scripts to avoid confusing test/tool SQL with application runtime SQL.
- Current runtime scan: 40 `lastrowid` references, 29 `INSERT OR IGNORE` / `INSERT OR REPLACE` candidates, 24 SQLite schema-introspection references, 46 SQLite date/time expression candidates, 40 SQLite trigger-DDL references, 945 qmark-bearing execute-call lines, 41 `LIKE` candidates, 45 `GROUP BY` candidates, and 74 tenant-ID comparison candidates.
- Added three regression tests for inventory scope, known blocking patterns, and review-only semantics. The PostgreSQL migration test suite now passes with 99 tests.
- This stage does not alter application runtime behaviour. It turns the remaining compatibility work into a traceable, source-located queue. Regex matches require SQL-context review and are not automatically defects.
- Regenerate using `python tools/build_postgres_remediation_inventory.py`.

The next implementation priority is to replace application `lastrowid` dependencies with explicit `INSERT ... RETURNING id`, then port runtime schema introspection and data migrations. PostgreSQL must remain opt-in until those changes and live dual-engine tests are complete.


## Stage 20 - explicit generated IDs (initial conversion slice)

- Added `db_compat.insert_returning_id()` as a shared helper: SQLite continues to use its native `lastrowid`; PostgreSQL uses an explicit `INSERT ... RETURNING <key>` operation through the adapter.
- Added `PostgresCursorAdapter.execute_returning_id()`. It accepts only plain INSERT statements, rejects an existing RETURNING clause, validates the returned identifier, and fails if the insert produces no row.
- Converted the default-school creation and demo/seed data inserts in `db.py` (school, teacher, session, class, subjects and students) to the explicit helper. The student ID is now stored before the enrollment insert rather than relying on a cursor side effect.
- Added SQLite and PostgreSQL-adapter unit tests. These tests use a fake PostgreSQL cursor; they are not live PostgreSQL integration tests.
- The remediation inventory still contains other `lastrowid` usages across route modules and generated patch scripts. They remain open and must be converted individually after reviewing each INSERT's true primary key and conflict behaviour. Do not enable PostgreSQL application traffic yet.

## Stage 21 — INSERT OR IGNORE compatibility

The PostgreSQL cursor adapter now rewrites a leading SQLite `INSERT OR IGNORE`
into PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` before qmark placeholder
conversion. The rewrite is centralized so existing application call sites can
continue using the shared adapter while the app remains on SQLite locally.

`INSERT OR REPLACE` is deliberately rejected: SQLite's delete-and-insert
behaviour is not equivalent to a generic PostgreSQL upsert and needs a
per-statement conflict target/update policy. Also note that PostgreSQL
`ON CONFLICT DO NOTHING` handles unique/exclusion conflicts, whereas SQLite
`OR IGNORE` can suppress additional constraint violations such as CHECK and
NOT NULL. Each inventoried call site must therefore be checked against its
table constraints before enabling PostgreSQL traffic. The adapter remains
opt-in; this stage does not switch `db.get_db()` to PostgreSQL.

## Stage 22 — PostgreSQL catalog helpers

- Added `postgres_catalog.py` helpers for table existence, ordered column names,
  and index existence using `information_schema` / `pg_indexes`.
- All schema/table/index values are bound parameters; no identifier interpolation
  is used. Non-public schemas are supported by an explicit schema argument.
- Added fake-connection regression tests for true/false results, parameter
  binding, and ordinal column order.
- These helpers are opt-in and are not yet wired into `db.py`; SQLite startup
  migrations still contain catalog SQL, PRAGMAs, and SQLite DDL rebuilds.
  No PostgreSQL runtime switch is made in this stage.

## Stage 23 — targeted date/time expression compatibility

- Replaced three reviewed runtime date calculations with bound UTC ISO dates or
  Python ISO-date arithmetic, preserving report output shape and ordering.
- Added reusable date helpers and focused tests; the static runtime date/time
  candidate count decreased from 46 to 44.
- The remaining date/time work is concentrated in SQLite startup migrations,
  trigger DDL, and timestamp defaults. It is not safe to rewrite those globally.

## Stage 24 — PostgreSQL UTC text timestamp defaults

- Added `tools/build_postgres_timestamp_defaults.py` and generated
  `postgres_timestamp_defaults.sql` for the four audited `server_timestamp`
  defaults that used SQLite `strftime(..., 'now')`.
- PostgreSQL uses `clock_timestamp() AT TIME ZONE 'UTC'` plus `to_char` to
  retain the existing `YYYY-MM-DDTHH:MM:SSZ` TEXT representation. The generator
  verifies the exact four-column inventory and rejects type/schema drift.
- Added deployment notes and tests for the exact inventory, UTC format, and
  fail-closed behaviour.
- The SQL is not applied automatically and has not been run against a live
  PostgreSQL server. These columns must remain TEXT for this conversion. SQLite
  defaults and IndexedDB/offline sync are unchanged.
- `CURRENT_TIMESTAMP` call sites remain under review because PostgreSQL's
  timestamp type/cast formatting may differ from SQLite's text representation.
  SQLite startup migration functions and trigger DDL are still not PostgreSQL
  compatible; do not switch application traffic to PostgreSQL yet.

### Stage 25 — read-only schema readiness gate

Added `postgres_required_schema.json`, a generated name-level manifest of the effective
SQLite schema after the application's registered migrations (schema version 99: 113
tables and 1,569 columns). This is a required-object checklist, not executable PostgreSQL
DDL and not a claim that SQLite types/defaults/triggers have been fully ported.

`postgres_schema.validate_schema_shape()` and
`tools/check_postgres_schema_readiness.py` compare a PostgreSQL target against that
manifest using PostgreSQL catalog views. The check is strictly read-only: it does not
create or alter tables, migrate rows, truncate data, or remove unknown objects. Missing
tables or columns fail the check; extra columns are reported but allowed so that
installation-specific extensions are not rejected automatically.

Run after provisioning a reviewed PostgreSQL schema and before any data-copy attempt:

```bash
export DATABASE_URL='postgresql://...'
python tools/check_postgres_schema_readiness.py --manifest postgres_required_schema.json
```

Exit status is zero only when all required table and column names exist; status 2 means
the target is incomplete. This gate does not validate SQL types, constraints, indexes,
foreign keys, trigger bodies, row contents, or application query compatibility. It must
not be treated as a schema installer or as permission to run the data-copy utility.
The script requires psycopg 3 and a reachable PostgreSQL server; neither is available
in this build environment, so execution against a live target remains outstanding.
The existing SQLite startup/migration path is unchanged.

Stage 25 isolated suite: 132 tests passed; Python compilation passed. Tests use fake
DB-API connections and validate read-only SQL shape and missing/extra object reporting.

### Stage 26 — safe additive PostgreSQL column migrations

Added `postgres_migration_ops.add_column_if_missing()` for explicit PostgreSQL
migration functions. It validates table existence, quotes simple identifiers,
uses an allowlist of column types, restricts defaults to safe literals or
current date/time keywords, requires a default for additive `NOT NULL` columns,
and verifies the type of an already-existing column before treating the
operation as idempotently complete. This primitive deliberately does not
translate or run the existing SQLite migration registry, and it is not wired
into application startup. Table rebuilds, backfills, constraints, indexes,
renames and trigger changes remain separate migration work.

Stage 26 validation: `tests/postgres` passed using isolated fake DB-API
connections; Python compilation passed. No live PostgreSQL instance or driver
is available in this environment, so generated DDL has not been executed
against PostgreSQL.

## Stage 27 update — first PostgreSQL-native table migration

Added migration 100 for the standalone `security_events` table. See
`POSTGRES_TABLE_MIGRATIONS.md`. It is explicitly registered but remains separate
from the active SQLite startup path. The migration validates its resulting
column names and data types, includes the audited school/time index and
append-only update/delete guards, and preserves the existing UTC text timestamp
representation. No live PostgreSQL execution was available in this environment.

## Stage 28 — PostgreSQL-native `platform_notifications` table

Added migration 101 for `platform_notifications`, ordered after the baseline
`schools` table and migration 100. The migration verifies the referenced
`schools.id` type before creating a BIGINT foreign key, retains TEXT timestamp
fields, adds the source index on `created_at DESC`, and validates the final
column, FK, and index shape. It is explicitly registered in the standalone
PostgreSQL registry and is not connected to Flask startup. Live PostgreSQL
execution remains outstanding.

## Stage 29 — activation_attempts (migration 102)

Added a PostgreSQL-native `activation_attempts` table migration based on the
captured effective SQLite schema. It preserves all 14 columns, uses BIGINT for
SQLite INTEGER values, keeps timestamp values as TEXT, and adds no guessed
foreign keys or secondary indexes because none exist in the source snapshot.
The migration verifies column types/nullability and fails closed if unexpected
foreign keys or secondary indexes are present. It is registered in the
standalone PostgreSQL migration runner only; Flask startup and SQLite remain
unchanged. Live PostgreSQL execution is still required before deployment.


## Stage 30 — educational_domains (migration 103)

Added a PostgreSQL-native migration for `educational_domains` from the effective
SQLite schema. It preserves all seven columns, maps SQLite INTEGER values to
BIGINT, retains the `(school_id, domain_key)` composite unique constraint, and
adds no foreign keys or secondary indexes because none are declared in the
source snapshot. The migration verifies column types/nullability, the exact
unique index shape, and the absence of unexpected foreign keys or indexes. It
is registered in the standalone PostgreSQL migration runner only; the active
Flask/SQLite startup path and browser IndexedDB behaviour are unchanged. Live
PostgreSQL execution remains outstanding.


## Stage 31 — status_history (migration 104)

Added a PostgreSQL-native migration for `status_history`, based on the effective
SQLite schema snapshot. The 12-column table uses `BIGINT` for SQLite integer
identifiers, a generated identity primary key, and retains `created_at` as TEXT.
The source declares no foreign keys, secondary indexes, or table-specific triggers,
so none are introduced. The migration validates the target columns, types,
nullability, foreign-key absence, and secondary-index absence before completing.

The migration is registered as version 104 in the standalone PostgreSQL runner.
It does not switch application traffic from SQLite or change browser IndexedDB
offline behaviour. Live PostgreSQL integration remains a separate validation step.


## Stage 34 — migration 107: `ai_outputs`

Added `postgres_migration_107_ai_outputs.py` after reviewing the effective SQLite schema snapshot and original table definition. The table has 15 columns, no declared foreign keys, two non-unique indexes (`idx_ai_outputs_school_feature` and `idx_ai_outputs_student`), a status CHECK constraint (`draft`, `approved`, `rejected`), and a tenant-stamping trigger. The PostgreSQL migration uses a BIGINT identity primary key, maps integer identifiers to BIGINT, preserves timestamp fields as TEXT, recreates both indexes, and ports tenant stamping as a BEFORE INSERT trigger. The migration validates the expected columns/types/nullability, exact index set, absence of foreign keys, and presence of the tenant trigger. It is registered as migration 107 and remains separate from SQLite startup. Validation is unit-test based; execution against a live PostgreSQL server remains outstanding.
