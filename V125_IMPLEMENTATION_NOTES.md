# Migration 125 — `class_login_codes`

Reviewed the `class_login_codes` definition in `postgres_effective_schema_snapshot.json` from Stage 51. The source table has 15 columns, no declared foreign keys, and three explicit indexes:

- `idx_class_login_codes_school` on `(school_id, class_id)`
- `ux_class_login_codes_code` unique on `(code)`
- `ux_class_login_codes_one_active` unique on `(class_id)` where `status = 'active'`

The PostgreSQL migration uses a BIGINT identity primary key, maps SQLite INTEGER columns to BIGINT, preserves timestamp fields as TEXT, retains the `active` default and the four-value status CHECK constraint, and recreates all three indexes. It deliberately does not add foreign keys or triggers absent from the SQLite source definition.

The migration validates columns/types/nullability, absence of foreign keys, the exact index set and key predicates, the status CHECK constraint, and absence of triggers. It is registered as migration 125 and remains separate from SQLite startup. Unit tests and Python compilation are run as part of Stage 52 validation; live PostgreSQL execution remains outstanding.
