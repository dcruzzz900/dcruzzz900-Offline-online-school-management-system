# Migration 119 implementation notes — billing_receipts

Source reviewed: `postgres_effective_schema_snapshot.json` from the Stage 45 archive.

The source table contains 10 columns, three foreign keys, two UNIQUE constraints
(`payment_id` and `receipt_number`), and two non-unique indexes. PostgreSQL uses
BIGINT for the generated receipt ID and references the existing BIGINT keys in
`billing_invoices` and `billing_payments`; `school_id` remains INTEGER to match
baseline `schools.id`. SQLite REAL maps to DOUBLE PRECISION. The timestamp-like
`issued_at` value remains TEXT for application compatibility.

The migration validates dependency key types, column types/nullability, exact
foreign-key targets, the primary/unique/lookup index set, and absence of triggers.
It is registered as migration 119 and is not imported by SQLite startup.

Validation is limited to automated tests and static compilation unless a live
PostgreSQL instance is separately configured and used.
