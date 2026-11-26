# Migration 129 — custom_fields

Source: `custom_fields` in `postgres_effective_schema_snapshot.json`.

- 21 columns ported.
- `id` uses a PostgreSQL BIGINT identity primary key.
- `school_id` remains INTEGER, matching the PostgreSQL baseline `schools.id` type.
- Other SQLite INTEGER columns are represented as BIGINT; TEXT values and timestamp strings remain TEXT.
- Preserved defaults for `is_required`, `is_unique`, `is_editable`, `is_active`, `is_archived`, `display_order`, `created_at`, and `updated_at`.
- Preserved the allowed `applies_to` values and scoped unique key.
- Recreated the scope lookup index and the active-label case-insensitive partial unique index.
- No source foreign keys or triggers were declared; validation rejects unexpected ones.
- Registered as migration 129. Does not change `db.py`, SQLite startup, or offline sync code.
