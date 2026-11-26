# Explicit INSERT RETURNING compatibility

`db_compat.insert_returning_id(cursor, sql, params, key="id")` is the cross-dialect helper.

- SQLite path: execute the statement and return SQLite's native `lastrowid`.
- PostgreSQL path: `PostgresCursorAdapter.execute_returning_id` appends `RETURNING <key>`, fetches the generated key, and returns it.
- The PostgreSQL method deliberately accepts only INSERT statements and a simple identifier as the key. It rejects pre-existing RETURNING clauses and inserts that return no row (for example, `ON CONFLICT DO NOTHING`).
- The helper assumes the requested key is the actual generated primary key. Review non-`id` primary keys explicitly and pass `key=` only after confirming the schema.

The first converted slice is the default-school/demo seed flow in `db.py`. Remaining call sites in `app.py`, route modules, `offline_sync.py`, `profile_routes.py`, and older patch scripts are still tracked by `postgres_remediation_inventory.json`. This is intentionally incremental; the PostgreSQL runtime switch remains disabled.
