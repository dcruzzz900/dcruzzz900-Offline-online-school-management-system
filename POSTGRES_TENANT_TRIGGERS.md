# PostgreSQL tenant propagation triggers (Stage 13)

This stage ports the 29 SQLite triggers classified as `tenant_scope_propagation` into 28 PostgreSQL `BEFORE INSERT` triggers. The two SQLite triggers on `students` are consolidated into one trigger because they overlap and should not rely on PostgreSQL trigger-name ordering.

## Generated artifacts

- `tools/build_postgres_tenant_triggers.py` — deterministic, fail-closed generator.
- `postgres_tenant_triggers.sql` — generated PL/pgSQL functions and triggers.
- `tests/postgres/test_postgres_tenant_triggers.py` — generator and contract tests.

## Preserved behavior

- Existing non-empty `NEW.tenant_id` values are retained.
- For the direct school relationships, a missing tenant is looked up using `NEW.school_id`.
- `enrollments` derives its tenant through `classes -> schools` using `NEW.class_id`.
- `scores` and `score_history` derive their tenant through `students -> classes -> schools` using `NEW.student_id`.
- `students` derives its `school_id` and tenant through its class when the source trigger conditions require it.
- The port uses `BEFORE INSERT` and assigns fields on `NEW`, avoiding the SQLite pattern of issuing a second UPDATE against the inserted row.

## Safety and rollout notes

The generator contains explicit reviewed table-to-parent mappings and checks source trigger relationship shapes and required columns in the effective schema snapshot. It refuses unexpected tables, source relationships, or missing columns. It does not install or execute the SQL.

The SQL is generated from the current v113 effective SQLite schema snapshot. Before applying it, validate the actual PostgreSQL schema, tenant identifier types, and parent-row integrity. In particular, a missing parent lookup yields a NULL tenant, consistent with the source subquery behavior; a separate data-integrity policy may choose to reject such inserts, but that would be a deliberate behavior change and is not silently introduced here.

The two `students` source triggers are intentionally combined: the combined function fills `school_id` when absent and fills `tenant_id` when absent/empty. Review this behavior alongside the application's existing student creation paths before rollout.

No live PostgreSQL server/driver is available in the build environment, so these are generator/contract tests, not PostgreSQL execution tests. This stage does not switch application traffic to PostgreSQL. SQLite local installations and browser IndexedDB/offline sync remain unchanged.
