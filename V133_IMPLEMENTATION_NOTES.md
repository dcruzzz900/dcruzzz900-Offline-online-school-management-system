# Migration 133 — offline_sync_tokens

Reviewed `offline_sync_tokens` in `postgres_effective_schema_snapshot.json` from Stage 59.

The source table contains four columns: `token TEXT PRIMARY KEY`, required `entity_type TEXT`, required `entity_id INTEGER`, and nullable `created_at TEXT DEFAULT CURRENT_TIMESTAMP`. It declares only its primary-key autoindex and no foreign keys or triggers.

The PostgreSQL migration uses TEXT for token/entity type/timestamp and BIGINT for the non-key entity identifier. PostgreSQL primary keys enforce NOT NULL for `token`; SQLite's legacy rowid-table handling of NULL values in non-integer primary keys can differ, so applications should supply a token as intended by the token's idempotency role. No FK was inferred for `entity_id`, because the source intentionally has no declared relationship and does not identify a single parent table.

The migration is registered as version 133 and remains separate from SQLite startup and the existing offline-sync path. Unit/fake-connection validation does not substitute for execution against a live PostgreSQL server.
