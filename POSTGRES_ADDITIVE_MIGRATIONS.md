# PostgreSQL additive schema migration operations

Stage 26 adds `postgres_migration_ops.add_column_if_missing()` as a narrowly
scoped primitive for future PostgreSQL-native, versioned migrations.

The helper:

- requires an existing target table and a simple, quoted identifier;
- accepts only an explicit allowlist of PostgreSQL column types;
- accepts only reviewed constant defaults or `CURRENT_TIMESTAMP` /
  `CURRENT_DATE` (no arbitrary SQL expressions);
- requires a safe default before adding a `NOT NULL` column;
- checks existing columns for type compatibility and fails on a mismatch;
- leaves existing data untouched and does not silently alter existing columns.

Example inside a reviewed `PostgresMigration.apply` function:

```python
from postgres_migration_ops import add_column_if_missing


def apply(conn):
    add_column_if_missing(
        conn, "schools", "external_code", "TEXT", nullable=True
    )
```

This is not an automatic converter for the 99 SQLite migration registry. It
supports additive columns only. SQLite table rebuilds, renamed columns, data
backfills, constraints, indexes, and all trigger behaviours must be ported as
separate reviewed PostgreSQL migrations. The helper is not wired into the
application's active startup path and has not been run against a live server
in this environment.
