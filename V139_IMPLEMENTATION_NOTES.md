# Migration 139 implementation notes — `parent_teacher_messages`

Source: `parent_teacher_messages` in `postgres_effective_schema_snapshot.json`.

- Ported all 10 source columns; `id` is a BIGINT identity primary key.
- Kept `school_id`, `teacher_id`, and `student_id` as INTEGER to match the referenced baseline tables; `parent_id` is BIGINT to match `parent_accounts.id`.
- Preserved the required message body and sender type, including the CHECK restriction to `parent` or `teacher`.
- Preserved `is_read INTEGER NOT NULL DEFAULT 0` and `created_at TEXT DEFAULT CURRENT_TIMESTAMP`.
- Preserved all four foreign keys. The parent-account relationship retains `ON DELETE CASCADE`; the school, teacher, and student relationships retain `NO ACTION`.
- Recreated `idx_parent_messages_teacher` on `(school_id, teacher_id, is_read)` and `idx_parent_messages_thread` on `(school_id, parent_id, teacher_id, student_id, created_at)`.
- Recreated the source AFTER INSERT tenant-stamping trigger. If `tenant_id` is NULL or empty, it is populated from the matching school.
- Added dependency key-type checks and catalog validation for columns, foreign keys, indexes, CHECK constraint, and trigger.
- Registered as migration 139. This migration remains separate from SQLite startup and does not alter the existing offline synchronization path.
- Unit tests and Python compilation are used for validation; no live PostgreSQL server was available for executing the DDL.
