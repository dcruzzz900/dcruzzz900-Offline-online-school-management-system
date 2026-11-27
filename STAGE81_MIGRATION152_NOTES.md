# Stage 81 — PostgreSQL migration 152

Implemented `school_custom_info` as a standalone PostgreSQL migration.

## Source reconciliation

The original table is created in `db.py` in the V61 schema migration. A later SQLite migration (`custom_school_info_v104`) adds `show_on_result`, so the effective schema contains ten columns. The migration preserves the source-defined case-insensitive unique index on `(school_id, LOWER(label))`.

## Safety boundaries

- No SQLite startup or migration code was changed.
- No application database selection was changed.
- No offline storage or synchronization code was changed.
- The PostgreSQL registry now includes version 152.
- Live PostgreSQL execution has not been tested.
