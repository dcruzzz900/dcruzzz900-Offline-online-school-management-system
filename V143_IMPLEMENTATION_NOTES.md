# Stage 70 — Migration 143: `role_assignment_audit`

Ported the 14-column audit table from the effective schema snapshot. `id`, `assignment_id`, `user_id`, and `actor_user_id` use BIGINT; `school_id` remains INTEGER. The migration recreates the school index and UPDATE/DELETE append-only guards, validates columns, constraints, index and triggers, and registers version 143. Standalone PostgreSQL migration only: SQLite startup and offline synchronization are unchanged. Live PostgreSQL execution has not yet been tested.
