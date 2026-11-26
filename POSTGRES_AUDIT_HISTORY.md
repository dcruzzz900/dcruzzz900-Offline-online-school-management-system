# PostgreSQL audit/history capture — Stage 17

This stage ports the two reviewed SQLite triggers that append rows to
`billing_payment_history` after inserts and qualifying updates to
`billing_payments`.

## Generated objects

- `app_capture_billing_payment_history()` — one PL/pgSQL trigger function.
- `trg_billing_payment_insert_history_pg` — AFTER INSERT.
- `trg_billing_payment_update_history_pg` — AFTER UPDATE OF `status`,
  `amount_ngn`, `payment_reference`, `provider`, and `invoice_id`.

The function preserves the source field mapping, action labels (`created`,
`confirmed`, `status_changed`, `changed`), NULL-aware change comparisons,
and `COALESCE(confirmed_by, 'system')` actor fallback. PostgreSQL
`IS DISTINCT FROM` is the NULL-safe equivalent of SQLite `IS NOT` here.

## Important source behavior retained

The SQLite UPDATE trigger lists `provider` in its `UPDATE OF` clause but does
not compare `provider` in its `WHEN` predicate. Consequently a provider-only
update does not create a history row. This port deliberately retains that
behavior rather than silently changing the audit contract. The update history
row uses the new school/invoice IDs and the old/new values exactly as the
source trigger does.

History rows are inserted inside the same transaction as the payment write;
if history insertion fails, the payment write fails too. Existing immutable
history guards from Stage 12 remain responsible for blocking later UPDATE or
DELETE operations on history rows.

## Apply and verification cautions

`postgres_audit_history.sql` is generated only; it has not been applied to a
PostgreSQL server in this environment. Apply it only after the target baseline
schema and earlier trigger stages are installed. Validate the SQL on the same
PostgreSQL major version and exercise payment insert, status transition,
amount/reference/invoice changes, NULL transitions, provider-only updates,
rollback behavior, and immutable-history enforcement in an integration DB.

This stage does not modify SQLite startup behavior, local SQLite databases,
or browser IndexedDB/offline synchronization. It does not wire the Flask app
to PostgreSQL; application-wide SQL portability and live integration remain
separate blockers.
