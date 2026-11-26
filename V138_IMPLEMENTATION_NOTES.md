# Migration 138 implementation notes — parent_students

Source: `parent_students` in `postgres_effective_schema_snapshot.json`.

- Ten source columns retained.
- `id` mapped to BIGINT identity primary key.
- `parent_id` BIGINT references `parent_accounts(id)` (BIGINT).
- `student_id` and `school_id` INTEGER reference baseline `students(id)` and `schools(id)` (INTEGER).
- `verified_by` is BIGINT; the source does not declare it as a foreign key.
- Unique `(parent_id, student_id)` and both source lookup indexes retained.
- Parent and student FKs retain ON DELETE CASCADE; school FK retains NO ACTION.
- Source tenant-stamping AFTER INSERT trigger recreated. `tenant_id` is NOT NULL in the source, so an empty string is the effective fallback trigger condition.
- SQLite startup and existing offline sync remain unchanged. No live PostgreSQL server execution was performed.
