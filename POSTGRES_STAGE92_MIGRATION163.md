# Stage 92 — V140 — Migration 163: student_ai_consent

Implemented a standalone PostgreSQL-native definition for the effective `student_ai_consent` table.

The migration preserves the 14 effective columns: `student_id`, `school_id`, `status`, `granted_by_type`, `granted_by_id`, `policy_version`, `granted_at`, `withdrawn_at`, `notes`, `tenant_id`, `granted_by_name`, `relationship`, `recorded_by`, and `recorded_at`. Timestamp-like values remain `TEXT` to match the SQLite source representation. The status domain remains `pending`, `granted`, or `withdrawn`, with `pending` as the default.

The migration also creates the existing `(school_id, status)` lookup index and a PostgreSQL BEFORE INSERT tenant-stamping trigger that reads `schools.tenant_id` when the incoming tenant is blank. No foreign key is added because the effective SQLite source table does not declare one.

Migration 163 is registered after migration 162. Registry assertions and the table-gap expectations were advanced to reflect the new migration and coverage totals.

## Verification

- PostgreSQL-focused test suite: **497 passed**.
- Python compilation: passed.
- Migration registry: **64 migrations**, versions **100–163**.
- Explicit PostgreSQL table definitions: **88 of 113**.
- Remaining table candidates: **25**.
- ZIP archive integrity: passed.

The full repository test run was also attempted. It is not clean in this environment: several pre-existing UI contract assertions fail, and the end-to-end scenario subprocesses cannot import Flask because Flask is not installed in the execution environment. These failures are separate from the PostgreSQL-focused suite.

SQLite startup, SQLite migrations, IndexedDB offline storage, and offline synchronization are not modified. No live PostgreSQL server is available here, so execution against a real PostgreSQL instance remains unverified.
