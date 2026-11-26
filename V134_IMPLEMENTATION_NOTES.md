# Migration 134 — fixed_activities_v2

Source: `postgres_effective_schema_snapshot.json` in the Stage 60 archive.

- 18 source columns ported. SQLite `INTEGER` identifiers/flags use BIGINT except `school_id`, which remains INTEGER to match the existing `schools.id` key. SQLite TEXT fields remain TEXT.
- Preserved the sole declared FK: `school_id -> schools.id`.
- Preserved partial unique index `idx_fixed_activities_v2_client_uuid` (`client_uuid IS NOT NULL`).
- Replaced source AFTER INSERT defaults trigger with a PostgreSQL BEFORE INSERT trigger that fills missing `client_uuid` and `updated_at` values.
- Replaced source AFTER UPDATE timestamp-touch trigger with a PostgreSQL BEFORE UPDATE trigger. When the caller leaves `updated_at` unchanged, it advances to current UTC time or one second after the previous timestamp to retain monotonicity.
- The module is registered as migration 134 only; it does not change `db.py`, SQLite startup, or browser/device offline code.
- Unit tests use a fake DB-API connection. No live PostgreSQL server was available for DDL execution/catalog validation.
