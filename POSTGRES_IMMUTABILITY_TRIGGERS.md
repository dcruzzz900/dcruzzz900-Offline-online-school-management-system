# PostgreSQL immutability trigger conversion

The generated `postgres_immutability_triggers.sql` ports the 30 SQLite triggers
classified as `immutability_guard` in `postgres_trigger_porting_plan.json`.

It includes append-only protections for audit, payment-history, consent-history,
score-history, publication-history and related records, plus immutable server
attendance timestamps. A shared PL/pgSQL trigger function raises SQLSTATE
`55000` with the original user-facing message.

## Safety

- This is not a complete port of all 158 triggers.
- It does not implement tenant stamping, sync timestamps, tombstones, uniqueness,
  or audit-history capture.
- Apply only after the target tables and columns exist.
- Test both allowed and rejected operations on a disposable PostgreSQL database.
- The application remains on SQLite until the complete migration and regression
  suite is validated.

Regenerate using `python tools/build_postgres_immutability_triggers.py`.
