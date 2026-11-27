# Stage 92 — PostgreSQL Table Gap Report

- Source tables inventoried: **113**
- Explicit PostgreSQL CREATE TABLE coverage: **88**
- Remaining table candidates: **25**
- Columns in remaining candidates: **332**
- Remaining foreign-key declarations: **33**
- Remaining indexes: **41**
- Live PostgreSQL catalog checked: **No**

Migration 163 adds the effective `student_ai_consent` table, its school/status index, and tenant-stamping trigger. The table retains all 14 effective columns and the `pending` / `granted` / `withdrawn` status domain.

These counts are static source-to-file reconciliation only. They do not prove that a live PostgreSQL database contains the table or that all runtime SQL is PostgreSQL-compatible.

## Remaining candidates

| Table | Columns | FKs | Indexes |
|---|---:|---:|---:|
| `schedule_slots` | 20 | 3 | 1 |
| `schedule_templates` | 13 | 3 | 1 |
| `schema_steps` | 2 | 0 | 1 |
| `school_days_v2` | 10 | 1 | 2 |
| `staff_documents` | 10 | 0 | 2 |
| `student_ai_consent_events` | 14 | 0 | 1 |
| `subject_room_requirements_v2` | 10 | 3 | 2 |
| `subscription_plans` | 12 | 0 | 2 |
| `sync_changes` | 17 | 0 | 2 |
| `sync_conflicts` | 20 | 1 | 2 |
| `sync_log` | 11 | 0 | 1 |
| `sync_tombstones` | 5 | 0 | 1 |
| `teacher_availability_v2` | 13 | 4 | 2 |
| `teacher_timetable_preferences_v2` | 12 | 2 | 1 |
| `teacher_workload_profiles_v2` | 12 | 2 | 2 |
| `timetable_approvals_v2` | 15 | 1 | 1 |
| `timetable_audit_v2` | 14 | 1 | 1 |
| `timetable_configurations_v2` | 19 | 0 | 2 |
| `timetable_conflicts_v2` | 16 | 1 | 1 |
| `timetable_entries` | 12 | 5 | 3 |
| `timetable_entries_v2` | 18 | 2 | 2 |
| `timetable_periods` | 11 | 1 | 2 |
| `timetable_rooms_v2` | 13 | 1 | 2 |
| `timetable_types_v2` | 10 | 1 | 2 |
| `timetable_versions_v2` | 23 | 1 | 2 |

## Limitations

- Column-level parity for already matched tables is not fully established by this table-coverage report.
- Foreign-key and index parity for all source tables remains to be reconciled.
- SQLite trigger semantics, runtime query compatibility, and live PostgreSQL integration remain unverified.
