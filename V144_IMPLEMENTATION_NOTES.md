# Stage 71 — Migration 144: `role_assignments`

Added standalone PostgreSQL migration 144 for `role_assignments`, based on the effective schema snapshot. It recreates the 20-column table, role/status CHECK constraints, foreign keys to `users(id)` and `schools(id)`, and the six secondary indexes for user, school, tenant, class, subject and department lookup. The migration validates column types/nullability and expected index names/shapes. It is registered in the standalone PostgreSQL migration registry.

This migration expects `users` and `schools` tables to already exist in the target PostgreSQL schema with compatible primary key types. It does not create those baseline tables or backfill data. SQLite startup, the SQLite database path, and offline synchronization are unchanged. Tests are contract/unit tests; live PostgreSQL execution has not been performed.
