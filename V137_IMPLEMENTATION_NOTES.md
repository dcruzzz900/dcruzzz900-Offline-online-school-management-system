# Migration 137 — `parent_consent_events`

- Ported all eight columns from `postgres_effective_schema_snapshot.json` in the Stage 63 archive.
- Preserved `action` as required TEXT with the source CHECK constraint limiting values to `granted` and `withdrawn`.
- Preserved `created_at` as nullable TEXT with `CURRENT_TIMESTAMP` default and nullable `policy_version` and `tenant_id`.
- Added foreign keys to `schools(id)`, `students(id)`, and `parent_accounts(id)`. Key types follow the referenced tables: school/student IDs are INTEGER, while parent account IDs are BIGINT.
- Reimplemented the source AFTER INSERT tenant-stamping trigger: when `tenant_id` is NULL or empty, it is populated from the matching school's tenant ID.
- The source declares no secondary indexes; only the primary-key index is created.
- Added validation for dependency key types, exact columns/nullability, all three foreign keys, action CHECK presence, exact index set, and tenant trigger presence.
- Registered as migration 137. It remains standalone and is not connected to SQLite startup or the existing offline-sync path. Live PostgreSQL execution remains outstanding.
