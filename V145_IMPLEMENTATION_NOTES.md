# Stage 72 — Migration 145: `role_assignment_permissions`

Added standalone PostgreSQL migration 145 for `role_assignment_permissions` based on the SQLite schema definition. It creates the four-column table (`id`, `assignment_id`, `permission`, `granted`), foreign key to `role_assignments(id)`, and the assignment lookup index. Migration validation checks column type/nullability and index shape, and migration 145 is registered in the standalone PostgreSQL registry.

This migration depends on Migration 144 (`role_assignments`) being present. It does not create or modify SQLite tables, alter SQLite startup, or change offline synchronization. Contract tests are included; live PostgreSQL execution has not been tested.
