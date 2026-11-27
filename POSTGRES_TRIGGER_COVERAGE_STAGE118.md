# PostgreSQL Trigger Coverage - Stage 118

Source (SQLite) triggers: **158**  |  PostgreSQL triggers: **121**  |  PostgreSQL functions: 36

| Result | Count |
|---|---:|
| Source triggers mapped to exactly one port | 158 |
| Source triggers unmapped | 0 |
| Errors | 0 |

## Source categories

| Category | Count |
|---|---:|
| `audit_or_history_capture` | 2 |
| `business_rule_or_other` | 2 |
| `cross_row_uniqueness` | 5 |
| `immutability_guard` | 30 |
| `offline_sync_timestamp` | 72 |
| `soft_delete_or_sync_tombstone` | 18 |
| `tenant_scope_propagation` | 29 |

## Reviewed consolidations

- `trg_students_tenant_stamp_pg` replaces `trg_students_stamp_tenant`, `trg_students_tenant_stamp`
- 36 pairs of `_sync_defaults` + `_sync_touch` triggers are each replaced by one `_sync_timestamp` trigger (`INSERT OR UPDATE`).

## Intentional timing changes

- AFTER->BEFORE: 101 trigger(s)

## Errors

None.

## What this does and does not mean

Coverage is **file-level only**: every SQLite trigger has an explicit, reviewed PostgreSQL port on the same table covering the same event, each port's function is defined, and each target table is created by the baseline or a migration. It does **not** show that any trigger body behaves like its SQLite original, nor that the SQL files apply on a real server. Run `tools/run_postgres_migrations_live.py` for that.
