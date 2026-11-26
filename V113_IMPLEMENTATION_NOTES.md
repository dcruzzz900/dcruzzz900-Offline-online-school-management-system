# V113 — PostgreSQL billing invoices migration

- Source: `billing_invoices` in `postgres_effective_schema_snapshot.json`.
- Columns: 13, including generated ID, school link, invoice number, plan and billing fields, status, timestamps, and optional notes/creator fields.
- Constraints: primary key; globally unique `invoice_number`; `school_id` references baseline `schools(id)`.
- Indexes: `idx_billing_invoices_status` and `idx_billing_invoices_school`, plus the primary-key and invoice-number unique indexes.
- Type mapping: generated ID to BIGINT identity; `school_id` to INTEGER to match baseline `schools.id`; SQLite REAL to DOUBLE PRECISION; timestamps remain TEXT for compatibility.
- Defaults retained: `amount_ngn=0`, `billing_days=365`, `status='pending'`, and `issued_at=CURRENT_TIMESTAMP`.
- Validation checks columns/nullability, school key type, exact foreign key and index set, and absence of triggers.
- Migration 113 is standalone; it is not wired into SQLite startup. Live PostgreSQL execution remains outstanding.
