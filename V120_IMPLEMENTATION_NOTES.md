# Migration 120 implementation notes

Table: `billing_reconciliation_exceptions`

Source: `postgres_effective_schema_snapshot.json` in the Stage 46 archive.

The migration creates the 12-column table with a BIGINT identity primary key, preserves the unique `exception_key`, and adds nullable BIGINT references to the already migrated `billing_payments` and `billing_invoices` tables. It recreates the three source lookup indexes (`invoice_id`, `payment_id`, and `status`). Text timestamps and source defaults are retained for application compatibility.

Validation checks dependency key types before DDL, then validates column types/nullability, exact foreign-key targets, expected indexes/unique index, and absence of triggers. No live PostgreSQL server was available for executing DDL against a real database.
