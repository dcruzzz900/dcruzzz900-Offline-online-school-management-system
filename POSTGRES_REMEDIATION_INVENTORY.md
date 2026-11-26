# PostgreSQL application remediation inventory

Scope: Python source excluding tests, virtual environments and caches.

This is a review queue, not evidence that every match is a defect. The SQL adapter already handles positional qmark conversion; dialect-specific constructs and generated IDs still need explicit remediation.

## Findings by category

| Category | Matches |
|---|---:|
| `lastrowid` | 40 |
| `insert_or_ignore_replace` | 29 |
| `sqlite_introspection` | 24 |
| `sqlite_datetime` | 46 |
| `sqlite_trigger_ddl` | 40 |
| `qmark_sql` | 945 |
| `case_insensitive_like` | 41 |
| `group_by` | 45 |
| `tenant_id_comparison` | 74 |

## Highest-volume files

| File | Findings |
|---|---:|
| `app.py` | 731 |
| `db.py` | 197 |
| `v61_routes.py` | 88 |
| `v63_spec.py` | 58 |
| `profile_routes.py` | 57 |
| `billing_finalization.py` | 23 |
| `v62_routes.py` | 23 |
| `v64_spec.py` | 22 |
| `offline_sync.py` | 20 |
| `announcements.py` | 11 |
| `v63_core.py` | 9 |
| `profile_core.py` | 8 |
| `result_fields.py` | 8 |
| `modify.py` | 6 |
| `modify2.py` | 5 |
| `role_charts.py` | 4 |
| `security_audit.py` | 3 |
| `local_backup.py` | 2 |
| `pdf_sheet.py` | 2 |
| `backup_db.py` | 1 |

## Required remediation order

1. Replace application `lastrowid` dependencies with explicit `INSERT ... RETURNING id` and test every insert path.
2. Port SQLite schema introspection and runtime migration execution to the versioned PostgreSQL migration runner.
3. Convert `INSERT OR IGNORE` / `INSERT OR REPLACE` individually after identifying intended conflict keys and delete/replace semantics.
4. Review date/time expressions, trigger DDL, and table rebuild migrations against PostgreSQL equivalents.
5. Review each `LIKE`, `GROUP BY`, and tenant comparison in its query context; preserve case and tenant isolation semantics.
6. Only then enable PostgreSQL selection in `get_db()` behind an explicit deployment setting and run the full application suite against both engines.

## Limitations

- Regex-based inventory; findings require SQL-context review.
- Qmark count is a line-level indicator, not a count of bound parameters.
- GROUP BY and LIKE are review candidates, not automatically invalid PostgreSQL SQL.
