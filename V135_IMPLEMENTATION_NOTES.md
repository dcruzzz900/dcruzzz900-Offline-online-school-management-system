# V135 — Stage 88 implementation notes

- Added standalone PostgreSQL migration 159: `ui_preferences`.
- Source: `migration_085_v107_ui_preferences` in `db.py`.
- Preserves six columns, `(kind, actor_id)` composite primary key, `font_scale` default 100, and `updated_at` default CURRENT_TIMESTAMP.
- Added exact schema/constraint/index/trigger validation and registry regression tests.
- Updated static reconciliation: 84/113 explicit table definitions; 29 candidates, 371 columns, 33 unresolved FK declarations, 44 unresolved indexes.
- SQLite startup and migrations, SQLite database selection, offline storage and offline synchronization are unchanged.
- Live PostgreSQL execution/catalog verification has not been performed.
