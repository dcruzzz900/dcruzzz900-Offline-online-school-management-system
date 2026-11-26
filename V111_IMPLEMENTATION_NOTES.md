# Migration 111 — billing_job_runs

## Source review

The effective SQLite schema snapshot defines `billing_job_runs` with seven
columns: `id`, `job_name`, `started_at`, `finished_at`, `status`, `result_json`,
and `error_message`. It has no declared foreign keys or triggers. The two
non-unique indexes are `idx_billing_job_runs_status` on `status` and
`idx_billing_job_runs_name_started` on `(job_name, started_at)`.

## PostgreSQL port

- `id` is a BIGINT identity primary key.
- Existing SQLite INTEGER semantics are mapped to PostgreSQL BIGINT.
- Timestamp strings and the result payload remain TEXT for compatibility.
- `started_at` defaults to `CURRENT_TIMESTAMP` and `status` defaults to
  `'running'`.
- Both source lookup indexes are recreated.
- No foreign key or trigger is introduced because the reviewed source has none.

## Validation

The migration validates all expected column names, PostgreSQL data types, and
nullability; rejects unexpected foreign keys and triggers; and checks the
exact index set and indexed columns. Automated tests cover migration metadata,
registry order, DDL contract, and validation failures.

The migration is standalone. It is not imported by `db.py`, does not alter
SQLite startup, and has not been executed against a live PostgreSQL server.
