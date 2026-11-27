# Stage 80 — PostgreSQL Table and Column Gap Reconciliation

Stage 80 continues the Stage 79 static reconciliation. It traces every source table that lacked an explicit PostgreSQL `CREATE TABLE` match and records the source columns, foreign keys, indexes, original SQLite `CREATE TABLE` SQL, and references found in PostgreSQL helper/trigger files.

## Results

- Source tables: **113**
- Tables with explicit PostgreSQL `CREATE TABLE` in the baseline or numbered migration files: **76**
- Tables without an explicit PostgreSQL `CREATE TABLE`: **37**
- Source columns in those 37 tables: **498**
- Foreign-key declarations in those tables: **36**
- Indexes in those tables: **52**

The 37 tables are concrete file-level DDL gaps in the scanned PostgreSQL baseline/migration sources. They are candidates for PostgreSQL table migrations unless an independently provisioned schema mechanism exists. A table name appearing in a trigger or helper script does not create the table and is not counted as coverage.

See `POSTGRES_TABLE_GAP_DETAILS_STAGE80.md` for the table-by-table summary and `POSTGRES_TABLE_GAP_DETAILS_STAGE80.json` for full column/FK/index/source-DDL detail.

## Validation

Run:

```bash
PYTHONPATH=. pytest -q tests/postgres/test_stage80_table_gap_report.py
python tools/reconcile_postgres_table_details.py
```

The test checks deterministic counts, the distinction between DDL and ancillary references, and the fact that no live PostgreSQL catalog was inspected.

## Still outstanding

This stage does not yet establish full schema parity. Column-level parity for the 76 explicitly matched tables, PostgreSQL types/defaults/constraints, complete FK/index parity, SQLite trigger conversion, application SQL compatibility, and live PostgreSQL execution remain to be validated.

## Safety boundary

Report/tooling only. No Migration 152 is created. The PostgreSQL registry is unchanged. SQLite startup, SQLite migrations, application database selection, offline storage, and offline synchronization are unchanged. Live PostgreSQL execution remains untested.
