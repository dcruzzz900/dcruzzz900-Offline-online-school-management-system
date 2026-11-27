# Stage 118 - Trigger-level coverage reconciliation

Stage 117 closed table-level coverage (112 of 113 source tables ported, `schema_steps` excluded).
This stage does the same for the 158 SQLite triggers, with a fail-closed static check.

## What was added

- `tools/reconcile_postgres_trigger_coverage.py` - maps every source trigger in
  `postgres_trigger_porting_plan.json` to a `CREATE TRIGGER` in the `postgres_*.sql` files using
  explicit naming rules only (same name, `<name>_pg`, `_sync_defaults`+`_sync_touch` ->
  `_sync_timestamp`, and one reviewed consolidation). No fuzzy matching.
- `POSTGRES_TRIGGER_COVERAGE_STAGE118.json` / `.md` - the generated report (`--write`).
- `tests/postgres/test_postgres_trigger_coverage.py` - repository-state test, report-freshness test
  and five fail-closed mutation tests.
- Also in this change set (written earlier, offline-tested only): `tools/run_postgres_migrations_live.py`
  and `tools/check_postgres_catalog_parity.py`, plus `tests/postgres/test_live_run_and_parity_tools.py`.

## Result

| | Count |
|---|---:|
| SQLite triggers | 158 |
| PostgreSQL triggers (121 distinct, 36 functions) | 121 |
| Source triggers mapped to exactly one port | 158 |
| Unmapped source triggers / errors | 0 / 0 |

121 = 30 immutability + 18 tombstone + 28 tenant + 36 sync-timestamp + 5 uniqueness + 2 audit + 2 business-rule.
The 37 fewer ports than sources are all reviewed consolidations: 36 sync pairs (`_sync_defaults` +
`_sync_touch` -> one `INSERT OR UPDATE` trigger) and the two `students` tenant triggers
(`trg_students_tenant_stamp`, `trg_students_stamp_tenant` -> `trg_students_tenant_stamp_pg`, documented in
`POSTGRES_TENANT_TRIGGERS.md`). 101 ports changed timing from `AFTER` to `BEFORE` (assign `NEW.*` instead of a
second `UPDATE`); this is intentional and reported as information.

## Fails closed on

unmapped source trigger; unmapped/stale PostgreSQL trigger; port on a different table; event not covered;
`UPDATE OF` column list narrower than the source; `EXECUTE FUNCTION` target not defined in any SQL file; trigger
on a table no migration/baseline creates; consolidation not in `CONSOLIDATIONS`.

## What this does not mean

File-level coverage only. It does not show that a trigger body behaves like its SQLite original, or that the SQL
files apply on a real server. No PostgreSQL server or driver was available, so nothing here has run on PostgreSQL.

## Verification

`tests/postgres`: 711 passed, 0 failed with a stand-in runner and a minimal `pytest` shim (no network to install
pytest); 34 tests needing `tmp_path` / `monkeypatch` fixtures were not executed. Re-run with real `pytest` before merging.

## Queued next

1. Run `tools/run_postgres_migrations_live.py --confirm-scratch --mode each --sql-before-sync` on a scratch
   PostgreSQL database and fix what fails (this also exercises the 8 trigger/default SQL files).
2. Review `tools/check_postgres_catalog_parity.py` output (ERROR first) against the migrated schema.
3. Behavioural trigger tests on a real server (tenant stamping, immutability errors, tombstones, sync timestamps), then
   application query compatibility.
