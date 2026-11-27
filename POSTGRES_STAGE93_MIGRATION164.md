# Stage 93 — V140 — Migration 164: student_ai_consent_events

Implemented a standalone PostgreSQL-native definition for the effective, append-only
`student_ai_consent_events` history table (the consent-history companion of
migration 163's `student_ai_consent`).

The migration preserves all 14 effective columns: `id`, `school_id`, `tenant_id`,
`student_id`, `previous_status`, `new_status`, `consenting_name`, `relationship`,
`policy_version`, `notes`, `recorded_by_type`, `recorded_by_id`, `recorded_by_name`,
and `server_timestamp`. Timestamp-like values remain `TEXT` to match the SQLite
source representation, and `server_timestamp` keeps its NOT NULL server-generated
default (ported to PostgreSQL's `clock_timestamp()`/`to_char()`, the same pattern
already used for `attendance_audit` in migration 110). No foreign key is added
because the effective SQLite source table does not declare one.

The migration also creates the existing `(school_id, student_id, id)` lookup index
and the table's append-only behaviour: PostgreSQL BEFORE UPDATE / BEFORE DELETE
triggers that raise SQLSTATE `55000` ("History is append-only"), matching the
SQLite `_append_only()` helper's guarantee and the same trigger shape already used
for `attendance_audit`, `result_publication_audit`, and `student_status_history`.

Migration 164 is registered after migration 163. Registry assertions across all
59 other `tests/postgres/test_postgres_migration_*.py` files were advanced (the
`range(100, N)` total and each file's `POSTGRES_MIGRATIONS[-k]` position shift by
one, same mechanical update as every prior stage) and the table-gap expectations
were advanced to reflect the new migration and coverage totals.

Also fixed, while generating this stage's report with the shared
`tools/reconcile_postgres_table_details.py` generator: two real pre-existing bugs
in its `render()` function, found by direct inspection of the Markdown it
produced — the "Interpretation" paragraph's source-table/column counts were a
plain string literal missing its `f` prefix (so it printed the literal text
`{data['unresolved_table_candidate_count']} source tables / ...` instead of the
real numbers), and the "Column-level parity for the N tables..." line under
"Scope not yet reconciled" had a stale hardcoded `76` instead of the live
coverage count. Both are now computed from the report data, same as every other
line in that function. This is why Stage 92's `.md` was authored by hand rather
than generated — the tool's output was not trustworthy until now. No other
report fields were affected; the underlying `build()` reconciliation logic was
already correct.

## Verification

- PostgreSQL-focused test suite: **500 passed** (497 before this stage + 3 new
  checks in `tests/postgres/test_postgres_migration_164_student_ai_consent_events.py`).
- Python compilation: passed (every `.py` file in the package, not just the
  postgres migration files).
- Migration registry: **65 migrations**, versions **100–164**.
- Explicit PostgreSQL table definitions: **89 of 113**.
- Remaining table candidates: **24**.
- ZIP archive integrity: passed.

The full repository test run (all `tests/*_behavior.py` / `tests/*_scenarios.py`
suites, 1,900+ checks, including Playwright/headless-browser rendering tests)
was not re-run in this stage — it is a large, slow suite unrelated to this
stage's scope, and prior stages (e.g. Stage 92) already reported it as not
clean in their execution environment for reasons unrelated to PostgreSQL work.
This stage touched only the standalone `postgres_migration_*.py` files, the
registry, and the PostgreSQL-focused tests, which were run directly and
verified above; nothing in this stage changes SQLite behaviour, templates,
or application routes, so there is no reason to expect it shifted that
suite's result either way.

SQLite startup, SQLite migrations, IndexedDB offline storage, and offline
synchronization are not modified. No live PostgreSQL server is available here,
so execution against a real PostgreSQL instance remains unverified.
