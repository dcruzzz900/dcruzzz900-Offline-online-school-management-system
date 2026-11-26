# PostgreSQL catalog compatibility helpers

Stage 22 adds `postgres_catalog.py` with parameterized helpers for checking
whether a table or index exists and retrieving a table's ordered column names.
They use PostgreSQL's `information_schema` and `pg_indexes`, avoiding SQLite's
`sqlite_master` and `PRAGMA table_info` for these specific operations.

The helpers are opt-in and are not wired into `db.py`: its startup migration
framework still depends on SQLite DDL, `executescript`, SQLite catalog SQL,
and SQLite-specific rebuild migrations. Do not switch the app's connection
factory until those migrations have a separately tested PostgreSQL path.

Identifiers are values, not SQL fragments, and are passed as bound parameters.
The default schema is `public`; callers using another schema must pass it
explicitly. These helpers intentionally do not emulate SQLite table DDL text,
foreign-key PRAGMAs, or SQLite migration behaviour.

Tests use a fake DB-API connection and validate query shape/parameter binding;
a live PostgreSQL catalog test remains required.
