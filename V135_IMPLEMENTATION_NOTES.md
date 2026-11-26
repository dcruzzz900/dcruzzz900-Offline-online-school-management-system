# Migration 135 — grading_config_audit

Source reviewed: `grading_config_audit` in `postgres_effective_schema_snapshot.json`.

- 15 columns; `id` is a BIGINT identity primary key.
- `school_id` remains INTEGER because the baseline `schools.id` key is INTEGER.
- Eight REAL score-limit values are represented as DOUBLE PRECISION.
- `affected_count` is BIGINT NOT NULL DEFAULT 0.
- `changed_at` remains TEXT DEFAULT CURRENT_TIMESTAMP for application compatibility.
- Foreign key: `school_id` -> `schools(id)`.
- Index: non-unique `(school_id, changed_at)`.
- No source triggers; the migration does not add any.

The migration is registered as version 135 but is not connected to SQLite startup. Automated tests validate the generated DDL and catalog-validation paths using a fake connection. A live PostgreSQL server was not available for execution in this stage.
