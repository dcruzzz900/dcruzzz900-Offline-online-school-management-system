# V148 — Stage 75 / PostgreSQL Migration 148

Implemented standalone PostgreSQL migration `148` (`create_subscription_history`) from the effective SQLite schema in `db.py`, inside `migration_060_v61`.

- Creates the 14-column `subscription_history` table.
- Preserves the source-defined `(school_id, id)` lookup index.
- Preserves append-only history semantics with PostgreSQL BEFORE UPDATE and BEFORE DELETE triggers using `app_reject_immutable_row`.
- Adds schema, primary-key, index, and trigger validation.
- Registers migration 148 only in `postgres_migration_registry.py`.
- Adds migration-specific unit tests.

Validation: migration-specific tests and the PostgreSQL test suite are run as part of Stage 75. No live PostgreSQL server execution is performed. This is a standalone PostgreSQL migration; it does not change SQLite startup, SQLite migrations, or offline synchronization.
