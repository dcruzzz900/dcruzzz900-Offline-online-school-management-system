# Migration 118 — billing_financial_audit

Source reviewed: `postgres_effective_schema_snapshot.json` in the Stage 44 archive.

The source table has ten columns, optional references to schools, billing payments,
and billing invoices, four non-unique indexes, and two SQLite triggers that reject
UPDATE and DELETE with `Financial audit records are immutable`.

The PostgreSQL migration uses BIGINT identity for its generated ID, INTEGER for the
baseline schools key, and BIGINT for payment and invoice keys. All optional foreign
key columns remain nullable. It recreates all four indexes and implements the
append-only behavior with PostgreSQL trigger functions. `created_at` remains TEXT
and retains the source CURRENT_TIMESTAMP default.

The migration is registered as version 118 and is not imported by SQLite startup.
No live PostgreSQL server was available for execution/catalog verification.
