# Migration 136 implementation notes — parent_accounts

## Source reviewed

`parent_accounts` in `postgres_effective_schema_snapshot.json` from the supplied Stage 62 archive.

## Ported schema

- 16 columns, retaining source names, nullability and defaults.
- `id` becomes a PostgreSQL BIGINT identity primary key.
- `school_id` remains INTEGER to match baseline `schools.id`.
- Other SQLite INTEGER values become BIGINT.
- TEXT fields remain TEXT, including `created_at` and `date_of_birth`.
- Unique `(school_id, username)` constraint is retained.
- Foreign key `school_id -> schools(id)` is retained.

## Trigger behavior

The SQLite source declares `tenant_id TEXT NOT NULL` but the AFTER INSERT trigger checks both NULL and empty string. A NULL tenant cannot pass the source column constraint, so the PostgreSQL trigger implements the effective empty-string case: after insert, it updates the inserted account's tenant ID from its referenced school. The PostgreSQL column remains NOT NULL; the migration does not silently loosen source integrity.

## Validation

The migration validates the school primary-key type, all column types/nullability, exact foreign-key relationship, primary and unique index set/definition, and expected trigger presence.

## Scope

Migration 136 is registered only in the standalone PostgreSQL migration registry. It is not imported by `db.py`, does not alter SQLite startup, and does not modify the existing offline synchronization path. Live PostgreSQL DDL execution was not performed in this stage.
