# Migration 140 — password_reset_tokens

## Source reviewed

`postgres_effective_schema_snapshot.json` from the preceding Stage 66 archive.

## Schema preserved

Seven columns: `id`, `account_type`, `account_id`, `token_hash`, `created_at`, `expires_at`, and `used_at`.

- `id`: PostgreSQL BIGINT identity primary key.
- `account_type`: required TEXT with CHECK values `staff` and `parent`.
- `account_id`: required BIGINT. No FK is declared because the source uses a polymorphic account reference.
- `token_hash`: required TEXT and unique.
- `created_at`: required TEXT with `CURRENT_TIMESTAMP` default.
- `expires_at`: required TEXT.
- `used_at`: nullable TEXT.

The source account lookup index `(account_type, account_id)` is recreated. No foreign keys or triggers are introduced.

## Validation

The migration validates the exact column set and nullability, expected primary/unique/check constraints, index set and definitions, and absence of foreign keys and triggers.

## Scope

Migration 140 is registered in the standalone PostgreSQL migration registry. It is not imported by SQLite startup and does not change the existing offline-sync implementation. Live PostgreSQL execution has not been performed as part of this stage.
