# V146 — Stage 73: staff_name_history

Added standalone PostgreSQL migration 146 for `staff_name_history`, based on the SQLite schema definition in `db.py`. It preserves the 16 columns and the `(school_id, user_id)` lookup index. Validation checks the exact column set and expected indexes.

This is a standalone PostgreSQL migration. It does not modify SQLite startup, SQLite migrations, or offline synchronization. Live PostgreSQL execution remains untested.
