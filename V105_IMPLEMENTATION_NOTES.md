# V105 — PostgreSQL migration 105: student_status_history

- Reviewed the effective SQLite definition in `db.py` and ported all 14 columns.
- Converted integer identifiers to `BIGINT` and used a PostgreSQL identity primary key.
- Preserved timestamp fields as `TEXT`; `server_timestamp` receives a UTC text default.
- Ported the declared lookup index `idx_student_status_history` on `(school_id, student_id, id)`.
- Ported the source append-only behavior with PostgreSQL `BEFORE UPDATE` and `BEFORE DELETE` triggers that raise `History is append-only`.
- No foreign keys were declared in the source schema; none were added.
- Added column, nullability, index, foreign-key, and trigger validation.
- Registered migration 105 in the standalone PostgreSQL migration registry. SQLite startup and browser IndexedDB behavior are unchanged.

## Validation

- Targeted PostgreSQL migration tests for migrations 100–105: 28 passed.
- Python compilation: passed.
- Full PostgreSQL test-directory collection was not run: unrelated existing tests resolve modules from other staged work directories and fail import during collection. The six targeted migration modules passed.

## Scope boundary

This is a standalone PostgreSQL schema migration only. It does not enable live PostgreSQL application connectivity, application-level database switching, or online/offline synchronization changes.
