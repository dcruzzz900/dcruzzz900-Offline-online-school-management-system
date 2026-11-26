# Stage 58 — Migration 131: `deferred_actions`

Reviewed the `deferred_actions` definition and index metadata in the effective SQLite schema snapshot. The table has 12 columns, a required relationship from `school_id` to baseline `schools(id)`, a unique `client_uuid`, and the `idx_deferred_actions_school` lookup index. The source has no triggers.

The PostgreSQL migration uses a BIGINT identity primary key, keeps `school_id` as INTEGER to match the baseline school key, and maps the non-FK `user_id` integer to BIGINT. It preserves `status` defaulting to `pending` and `created_at` as TEXT with its `CURRENT_TIMESTAMP` default. The unique client UUID and school foreign key are named constraints; the explicit school lookup index is recreated.

Validation checks all 12 column types/nullability, exact constraint and foreign-key definitions, the exact index set and key columns, and absence of triggers. The migration is registered as version 131 in the standalone PostgreSQL migration registry. It is not connected to SQLite startup and does not alter the existing offline-sync path. Live PostgreSQL execution remains outstanding.
