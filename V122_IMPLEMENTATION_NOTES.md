# Migration 122 implementation notes — billing_report_downloads

Source: `billing_report_downloads` in `postgres_effective_schema_snapshot.json` from Stage 48.

- Nine source columns; `id` is a PostgreSQL BIGINT identity primary key and SQLite INTEGER `row_count` is BIGINT.
- Optional `actor_name`, `start_date`, and `end_date` remain nullable.
- `created_at` remains TEXT with `CURRENT_TIMESTAMP` default for compatibility.
- Recreates the source `created_at` lookup index.
- Reproduces both source immutability triggers (UPDATE and DELETE rejection).
- No foreign keys are declared by the source schema.
- Standalone migration only; no SQLite startup or application database selection changes.
- Live PostgreSQL DDL execution was not performed in this stage.
