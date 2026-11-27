# Stage 115 — Detailed PostgreSQL Table Gap Report

- Source schema version: **99**
- Required source tables: **113**
- Tables with explicit PostgreSQL CREATE TABLE: **111**
- Tables without explicit PostgreSQL CREATE TABLE: **2**
- Columns in unresolved tables: **22**
- Foreign-key declarations in unresolved tables: **1**
- Indexes in unresolved tables: **3**

## Table-by-table findings

These are source tables for which no explicit CREATE TABLE statement was found in the numbered PostgreSQL migration files or `postgres_schema_base.sql`. A reference from a trigger/helper file is not counted as table creation.

| Table | Columns | FKs | Indexes | Other PostgreSQL references |
|---|---:|---:|---:|---|
| `schema_steps` | 2 | 0 | 1 | `tools/build_postgres_effective_schema_snapshot.py` |
| `sync_conflicts` | 20 | 1 | 2 | `postgres_tenant_triggers.sql`, `tools/build_postgres_tenant_triggers.py` |

## Interpretation

The table-level result is a concrete file-level gap list: **2 source tables / 22 columns** have no explicit PostgreSQL table-creation statement in the scanned baseline and migration files. The report also inventories source foreign keys, indexes, and non-DDL references.

It is still not a live-catalog result. The listed tables are outstanding PostgreSQL DDL candidates unless another externally provisioned schema mechanism is documented. Do not mark them migrated based only on trigger/helper references.

## Scope not yet reconciled

- Column-level parity for the 111 tables with explicit CREATE TABLE statements.
- PostgreSQL type, nullability, default, identity, CHECK and UNIQUE parity for every table.
- Foreign-key and index parity for all 113 tables.
- Conversion/validation of all 158 SQLite triggers and any views.
- Application query compatibility and live PostgreSQL catalog/integration tests.

## Safety boundary

This report is generated from the current PostgreSQL baseline and numbered migrations. It does not change SQLite startup, SQLite migrations, database selection, or offline storage/synchronization. Live PostgreSQL execution has not been performed.
