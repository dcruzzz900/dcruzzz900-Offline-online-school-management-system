# Migration 116 — billing_payment_history

Source: `billing_payment_history` in `postgres_effective_schema_snapshot.json` from the Stage 42 archive.

The source table contains 13 columns and three foreign keys. Its `payment_id` points to `billing_payments.id` (BIGINT in migration 115), `school_id` points to baseline `schools.id` (INTEGER), and nullable `invoice_id` points to `billing_invoices.id` (BIGINT in migration 113). The two REAL amount-history columns are represented as DOUBLE PRECISION. Timestamp and descriptive fields remain TEXT, retaining the source `CURRENT_TIMESTAMP` default for `created_at`.

The source declares two indexes: `(payment_id, created_at)` and `(school_id, created_at)`. It also declares BEFORE UPDATE and BEFORE DELETE SQLite triggers that abort with `Payment history records are immutable`. Migration 116 ports both guards using a PostgreSQL trigger function and row-level triggers.

The migration validates dependency key types before DDL, then checks column types/nullability, the exact foreign-key set, exact index set/definitions, and presence of both immutable triggers. It is registered in the standalone PostgreSQL registry only. It is not imported by `db.py`, does not change SQLite startup, and does not alter browser IndexedDB/offline synchronization.

Validation performed for this stage is automated unit testing with a fake connection and Python compilation. No live PostgreSQL server was available, so actual DDL execution and PostgreSQL catalog behavior remain to be verified in a real PostgreSQL environment.
