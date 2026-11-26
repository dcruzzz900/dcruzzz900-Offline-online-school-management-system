# Migration 121 — billing_renewal_recovery

Source: `postgres_effective_schema_snapshot.json` from the Stage 47 archive.

The migration ports all nine columns and the source table's unique constraint on
`(invoice_id, attempt_no)`, foreign keys to `billing_invoices(id)` and
`schools(id)`, and explicit index `idx_billing_recovery_status(status,
next_attempt_at)`. The PostgreSQL key types follow the referenced tables in the
current project schema: invoice ID is BIGINT; baseline school ID is INTEGER.

Timestamp-like values remain TEXT to preserve current application formatting
and compatibility. The migration is registered as version 121 and remains
separate from SQLite startup. Tests use a fake connection for catalog-validation
logic; they do not replace execution against a live PostgreSQL server.
