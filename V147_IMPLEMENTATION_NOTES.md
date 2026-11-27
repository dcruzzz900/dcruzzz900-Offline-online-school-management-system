# V147 — Stage 74 / PostgreSQL Migration 147

Implemented standalone PostgreSQL migration `147` (`create_score_audit`) from the effective SQLite schema in `db.py`, inside `migration_060_v61`.

- Creates the 32-column `score_audit` table.
- Preserves both source indexes: `(school_id, term_id, class_id, subject_id)` and `(school_id, student_id)`.
- Preserves append-only history semantics with PostgreSQL BEFORE UPDATE and BEFORE DELETE triggers using the existing `app_reject_immutable_row` helper.
- Adds schema, primary-key, index, and trigger validation.
- Registers migration 147 only in `postgres_migration_registry.py`.
- Updates PostgreSQL registry expectations in tests and adds migration-specific tests.

Validation: `PYTHONPATH=. pytest -q tests/postgres` passed. No live PostgreSQL server execution was performed. This is a standalone PostgreSQL migration; it does not change SQLite startup, SQLite migrations, or offline synchronization.
