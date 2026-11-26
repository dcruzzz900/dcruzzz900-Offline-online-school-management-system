# Migration 130 — custom_field_values

- Source: `custom_field_values` in `postgres_effective_schema_snapshot.json`.
- Ten columns; BIGINT identity primary key and BIGINT identifier fields.
- `entity_type` CHECK: `student` or `staff`.
- UNIQUE `(field_id, entity_id)`.
- `idx_custom_values_entity` on `(school_id, entity_type, entity_id)`.
- Partial unique `ux_custom_values_unique` on `(field_id, unique_value)` where `unique_value IS NOT NULL`.
- `updated_at` remains TEXT with `CURRENT_TIMESTAMP` default.
- No source foreign keys or triggers; none added.
- Registered as migration 130. Standalone PostgreSQL migration only; SQLite startup is unchanged.
- Live PostgreSQL execution has not been performed.
