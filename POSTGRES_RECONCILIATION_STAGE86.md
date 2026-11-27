# Stage 86 — PostgreSQL schema reconciliation after Migration 157

| Measure | Current static result |
|---|---:|
| Source SQLite tables | 113 |
| Explicit PostgreSQL table definitions | 82 |
| Unresolved table candidates | 31 |
| Columns in unresolved candidates | 383 |
| Unresolved foreign-key declarations | 33 |
| Unresolved indexes | 46 |
| Registered PostgreSQL migrations | 58 (100–157) |

## Migration 157

`signups` is now explicitly created by the standalone PostgreSQL migration. Its effective 13-column shape is taken from `migration_052_auth_signup_audit_spec` in `db.py`. The migration preserves the pending signup status default, optional user and school references, both foreign keys, and the `(school_id, signup_status)` index.

## Remaining table candidates

The 31 candidates are listed in `POSTGRES_RECONCILIATION_STAGE86.json`. They still require source review and dependency ordering. The next candidate must be selected from the actual remaining list, not assumed from a prior conversational suggestion.

## Limitations

- Static DDL/source comparison only; no live PostgreSQL catalog was queried.
- Explicit CREATE TABLE coverage does not prove column/default/constraint parity for matched tables.
- Foreign-key, index and trigger parity remain separate work items.
- Application SQL compatibility and live PostgreSQL execution have not been tested.

## Safety boundary

Migration 157 is standalone PostgreSQL DDL. It does not switch application database selection, change SQLite startup or migrations, or alter offline storage/synchronization.
