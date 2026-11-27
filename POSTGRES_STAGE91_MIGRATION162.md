# Stage 91 — V139 — Migration 162: school_ai_settings

Implemented a standalone PostgreSQL-native definition for the effective `school_ai_settings` table. The migration preserves all 15 columns, including the later nullable `tenant_id` addition, and retains the SQLite defaults: AI disabled by default, student-data processing disabled by default, feature toggles as defined by the source schema, and a 365-day retention default.

Validation checks column names/types/nullability, primary-key constraint/index, and absence of unexpected foreign keys or triggers. Migration 162 is registered after migration 161.

SQLite startup, SQLite migrations, IndexedDB offline storage, and offline synchronization are not modified. No live PostgreSQL server is available in this environment, so execution against a real PostgreSQL instance remains unverified.
