# Stage 101 — Detailed PostgreSQL Table Gap Report

- Source schema version: **99**
- Required source tables: **113**
- Tables with explicit PostgreSQL CREATE TABLE: **97**
- Tables without explicit PostgreSQL CREATE TABLE: **16**
- Columns in unresolved tables: **208**
- Foreign-key declarations in unresolved tables: **20**
- Indexes in unresolved tables: **26**

## Table-by-table findings

These are source tables for which no explicit CREATE TABLE statement was found in the numbered PostgreSQL migration files or `postgres_schema_base.sql`. A reference from a trigger/helper file is not counted as table creation.

| Table | Columns | FKs | Indexes | Other PostgreSQL references |
|---|---:|---:|---:|---|
| `schema_steps` | 2 | 0 | 1 | `tools/build_postgres_effective_schema_snapshot.py` |
| `staff_documents` | 10 | 0 | 2 | None found |
| `subject_room_requirements_v2` | 10 | 3 | 2 | `postgres_sync_timestamp_triggers.sql` |
| `sync_changes` | 17 | 0 | 2 | None found |
| `sync_conflicts` | 20 | 1 | 2 | `postgres_tenant_triggers.sql`, `tools/build_postgres_tenant_triggers.py` |
| `sync_log` | 11 | 0 | 1 | `postgres_tenant_triggers.sql`, `tools/build_postgres_tenant_triggers.py` |
| `sync_tombstones` | 5 | 0 | 1 | `postgres_tombstone_triggers.sql`, `tools/build_postgres_tombstone_triggers.py` |
| `teacher_timetable_preferences_v2` | 12 | 2 | 1 | `postgres_sync_timestamp_triggers.sql` |
| `teacher_workload_profiles_v2` | 12 | 2 | 2 | `postgres_sync_timestamp_triggers.sql` |
| `timetable_approvals_v2` | 15 | 1 | 1 | `postgres_sync_timestamp_triggers.sql` |
| `timetable_audit_v2` | 14 | 1 | 1 | `postgres_sync_timestamp_triggers.sql` |
| `timetable_conflicts_v2` | 16 | 1 | 1 | `postgres_sync_timestamp_triggers.sql` |
| `timetable_entries` | 12 | 5 | 3 | `postgres_sync_timestamp_triggers.sql`, `postgres_tenant_triggers.sql`, `postgres_tombstone_triggers.sql`, `tools/build_postgres_tenant_triggers.py`, `tools/build_postgres_tombstone_triggers.py` |
| `timetable_entries_v2` | 18 | 2 | 2 | `postgres_migration_166_school_days_v2.py`, `postgres_sync_timestamp_triggers.sql` |
| `timetable_periods` | 11 | 1 | 2 | `postgres_sync_timestamp_triggers.sql`, `postgres_tenant_triggers.sql`, `postgres_tombstone_triggers.sql`, `tools/build_postgres_tenant_triggers.py`, `tools/build_postgres_tombstone_triggers.py` |
| `timetable_versions_v2` | 23 | 1 | 2 | `postgres_sync_timestamp_triggers.sql` |

## Interpretation

The table-level result is a concrete file-level gap list: **16 source tables / 208 columns** have no explicit PostgreSQL table-creation statement in the scanned baseline and migration files. The report also inventories source foreign keys, indexes, and non-DDL references.

It is still not a live-catalog result. The listed tables are outstanding PostgreSQL DDL candidates unless another externally provisioned schema mechanism is documented. Do not mark them migrated based only on trigger/helper references.

## Scope not yet reconciled

- Column-level parity for the 97 tables with explicit CREATE TABLE statements.
- PostgreSQL type, nullability, default, identity, CHECK and UNIQUE parity for every table.
- Foreign-key and index parity for all 113 tables.
- Conversion/validation of all 158 SQLite triggers and any views.
- Application query compatibility and live PostgreSQL catalog/integration tests.

## Safety boundary

This report is generated from the current PostgreSQL baseline and numbered migrations. It does not change SQLite startup, SQLite migrations, database selection, or offline storage/synchronization. Live PostgreSQL execution has not been performed.
