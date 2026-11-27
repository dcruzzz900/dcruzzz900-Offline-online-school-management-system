# Stage 82 — PostgreSQL Migration 153: `result_custom_fields`

## Source

The effective SQLite definition is `migration_082_v104_result_custom_fields` in `db.py` (schema V104). The table has ten columns and one explicit case-insensitive unique index. The source definition declares no foreign keys or triggers.

## PostgreSQL implementation

- Added `postgres_migration_153_result_custom_fields.py`.
- Preserved all ten source columns and defaults.
- Used a PostgreSQL identity primary key.
- Preserved `ux_result_custom_fields_label` on `(school_id, LOWER(label))`.
- Added validation for exact column shape, expected indexes, and absence of unexpected foreign keys/triggers.
- Registered Migration 153 in `postgres_migration_registry.py` only.
- Added migration-specific tests and updated registry regression expectations.

## Updated static reconciliation

After adding Migration 153 and accounting for Migration 152, the scanner reports:

| Measure | Current result |
|---|---:|
| Source tables | 113 |
| Explicit PostgreSQL table definitions | 78 |
| Remaining table DDL candidates | 35 |
| Columns in remaining candidates | 478 |
| Foreign-key declarations in remaining candidates | 36 |
| Indexes in remaining candidates | 50 |

These are static source-to-file comparisons, not a live PostgreSQL catalog check. Column/type/default parity for already-created tables, all trigger conversions, application SQL compatibility, and live integration remain outstanding.

## Tests

`PYTHONPATH=. pytest -q tests/postgres` — all tests passed.

## Safety boundary

This is a standalone PostgreSQL migration. It does not switch application database selection, change SQLite startup or SQLite migration execution, or alter offline storage/synchronization. Live PostgreSQL execution has not been performed.
