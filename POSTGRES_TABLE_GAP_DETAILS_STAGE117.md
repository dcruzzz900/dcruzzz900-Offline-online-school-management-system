# Stage 117 — Detailed PostgreSQL Table Gap Report

- Source schema version: **99**
- Required source tables: **113**
- Tables with explicit PostgreSQL CREATE TABLE: **112**
- Tables deliberately excluded (not to be ported): **1**
- Tables without explicit PostgreSQL CREATE TABLE: **0**
- Columns in unresolved tables: **0**
- Foreign-key declarations in unresolved tables: **0**
- Indexes in unresolved tables: **0**

## Table-by-table findings

These are source tables for which no explicit CREATE TABLE statement was found in the numbered PostgreSQL migration files or `postgres_schema_base.sql`. A reference from a trigger/helper file is not counted as table creation.

| Table | Columns | FKs | Indexes | Other PostgreSQL references |
|---|---:|---:|---:|---|
| _none_ | 0 | 0 | 0 | |

## Deliberately excluded tables

These source tables are intentionally not ported. Each exclusion is declared in `EXCLUDED_TABLES` with a reason, and the report fails if an excluded table does not exist or later gains an explicit PostgreSQL CREATE TABLE.

| Table | Columns | Indexes | Reason |
|---|---:|---:|---|
| `schema_steps` | 2 | 1 | SQLite's own named-migration bookkeeping (read and written only by the SQLite migration runner in db.py). PostgreSQL tracks applied migrations in its own app_schema_migrations table, which carries a checksum per migration. |

## Interpretation

Table-level coverage is complete at the file level: every one of the 113 source tables either has an explicit PostgreSQL CREATE TABLE (112) or is deliberately excluded with a stated reason (1).

This is still not a live-catalog result: no explicit CREATE TABLE statement has been executed against a PostgreSQL server, and matching a statement in a file does not prove type, default, constraint or index parity.

## Scope not yet reconciled

- Column-level parity for the 112 tables with explicit CREATE TABLE statements.
- PostgreSQL type, nullability, default, identity, CHECK and UNIQUE parity for every table.
- Foreign-key and index parity for all 113 tables.
- Conversion/validation of all 158 SQLite triggers and any views.
- Application query compatibility and live PostgreSQL catalog/integration tests.

## Safety boundary

This report is generated from the current PostgreSQL baseline and numbered migrations. It does not change SQLite startup, SQLite migrations, database selection, or offline storage/synchronization. Live PostgreSQL execution has not been performed.
