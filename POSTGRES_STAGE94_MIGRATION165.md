# Stage 94 — V140 — Migration 165: subscription_plans

Implemented a standalone PostgreSQL-native definition for the effective
`subscription_plans` table (the platform's trial/basic/standard/premium plan
catalog).

## Why this table, next

The remaining 24 candidates after Stage 93 split into two groups:

- Tables whose SQLite source declares foreign keys into other **still-unported**
  tables — `schedule_slots` (references `school_days_v2` and `schedule_templates`,
  neither ported yet), the `timetable_*_v2`/`teacher_*_v2` family, and the
  `sync_*`/tombstone group. Porting any of these correctly means porting their
  dependencies first (or together), which is a bigger, riskier unit of work.
- Tables with **no foreign keys at all**, portable standalone the same way
  migrations 163/164 were.

`subscription_plans` is in the second group: 12 columns, 0 foreign keys, 2
source indexes (the implicit unique index behind `code UNIQUE` plus the named
`idx_subscription_plans_active`), and confirmed by grep across `app.py` and
every existing `postgres_migration_*.py` file that nothing anywhere joins to
it by `id` — the application always looks a plan up by its stable `code`
string. That makes it safe to port in isolation, unlike `schedule_slots`.

## What the migration does

Preserves all 12 effective columns: `id`, `code`, `name`, `price_ngn`,
`billing_days`, `max_students`, `max_teachers`, `max_storage_mb`,
`features_json`, `is_active`, `created_at`, `updated_at`. `price_ngn` (SQLite
`REAL`) maps to `DOUBLE PRECISION`, and the 0/1 boolean-like `is_active` flag
maps to `BIGINT`, both matching the conversion already used throughout this
migration series (e.g. the billing-amount migrations, `parent_accounts`).
`code` keeps its `UNIQUE` constraint; the `(is_active)` lookup index is
recreated under its original name. No foreign key is added, matching the
source. No application-managed triggers are expected on this table (unlike
163/164, it isn't tenant-stamped or append-only), and the migration's
verification step explicitly asserts that.

Migration 165 is registered after migration 164. Registry assertions across
all 60 other `tests/postgres/test_postgres_migration_*.py` files were advanced
the same mechanical way as every prior stage (the `range(100, N)` total and
each file's `POSTGRES_MIGRATIONS[-k]` position shift by one), and the
table-gap expectations were advanced to reflect the new migration and
coverage totals.

## Verification

- PostgreSQL-focused test suite: **503 passed** (500 before this stage + 3 new
  checks in `tests/postgres/test_postgres_migration_165_subscription_plans.py`).
- Python compilation: passed (whole package).
- Migration registry: **66 migrations**, versions **100–165**.
- Explicit PostgreSQL table definitions: **90 of 113**.
- Remaining table candidates: **23** — all of them now either carry a
  foreign key into an unported table, or belong to the
  `timetable_*`/`sync_*`/`teacher_*` dependency clusters flagged above.
- ZIP archive integrity: passed.

As in Stage 93, the full 1,900+-check application regression suite (including
Playwright/headless-browser rendering tests) was not re-run — out of scope
for this standalone migration track, which touches only
`postgres_migration_*.py` files, the registry, and the PostgreSQL-focused
tests. Nothing in this stage changes SQLite behaviour, templates, or
application routes.

SQLite startup, SQLite migrations, IndexedDB offline storage, and offline
synchronization are not modified. No live PostgreSQL server is available
here, so execution against a real PostgreSQL instance remains unverified.

## Queued next

The remaining 23 tables now genuinely need dependency-ordered work rather than
one more standalone pick:

1. `school_days_v2` and `schedule_templates` first (both are leaf dependencies
   with no further unported references of their own, as far as this report's
   static scan can tell) — this unblocks `schedule_slots`.
2. Then `schedule_slots` itself, which unblocks `teacher_availability_v2` and
   the rest of the `timetable_*_v2` family that reference it.
3. The `sync_changes` / `sync_conflicts` / `sync_log` / `sync_tombstones`
   group and `staff_documents` have no further blockers and could be done in
   any order alongside the above.
4. `schema_steps` is SQLite's own internal migration-bookkeeping table (which
   SQLite `STEPS` have been applied) — it has no PostgreSQL-side equivalent
   need, since this track already has its own parallel bookkeeping via
   `postgres_migration_registry.py`/`POSTGRES_MIGRATIONS`. Worth flagging to
   Austin rather than silently porting it as if it were ordinary app data.
