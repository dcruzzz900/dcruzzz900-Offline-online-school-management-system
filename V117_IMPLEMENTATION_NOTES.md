# Migration 117 — billing_adjustments

Reviewed source: `postgres_effective_schema_snapshot.json` in the Stage 43 archive.

The source table has 18 columns, foreign keys to `schools`, `billing_payments`, and `billing_invoices`, two named non-unique indexes, and a unique constraint on `reference`. The migration uses a BIGINT identity key; `school_id` is INTEGER to match the baseline `schools.id`; `payment_id` and `invoice_id` are BIGINT to match migrations 115 and 113. SQLite REAL maps to DOUBLE PRECISION. Timestamp values remain TEXT.

The apply function validates dependency key types before DDL, then validates the resulting column shape, foreign keys, exact index set, unique reference index, and absence of triggers. Migration 117 is registered in the standalone PostgreSQL registry only. SQLite startup and offline synchronization are not modified.

Validation in this stage is unit-test and compilation based. A live PostgreSQL server was not available, so execution of the DDL and catalog validation against PostgreSQL remain outstanding.
