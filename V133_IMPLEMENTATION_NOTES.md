# V133 — Stage 85 implementation notes

Stage 85 added standalone PostgreSQL migration 156 for `signup_codes`.

# V134 — Stage 86 implementation notes

Added standalone PostgreSQL migration 157 for `signups`, ported from `migration_052_auth_signup_audit_spec` in `db.py`. The migration preserves all 13 source columns, the pending status default, user/school foreign keys, and school/status lookup index. Updated the explicit migration registry, registry regression tests, migration inventory, and Stage 86 static reconciliation report.

PostgreSQL test suite results are recorded separately in the Stage 86 delivery summary. No live PostgreSQL execution was performed. SQLite startup, SQLite migrations, database selection, offline storage, and offline synchronization were not modified.

## V135 — Stage 87 / PostgreSQL Migration 158

Added standalone PostgreSQL DDL for `school_fee_summary`, preserving the effective six-column SQLite schema, amount defaults, timestamp default, and school/id index. SQLite startup, SQLite migrations, offline storage, and synchronization are unchanged. Live PostgreSQL execution has not been tested.
