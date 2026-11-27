# Stage 84 — PostgreSQL schema reconciliation after Migration 155

| Measure | Current static result |
|---|---:|
| Source SQLite tables | 113 |
| Explicit PostgreSQL table definitions | 80 |
| Unresolved table candidates | 33 |
| Columns in unresolved candidates | 414 |
| Unresolved foreign-key declarations | 36 |
| Unresolved indexes | 49 |
| Registered PostgreSQL migrations | 56 (100–155) |

## Unresolved table candidates

- `schedule_slots` — 20 columns
- `schedule_templates` — 13 columns
- `schema_steps` — 2 columns
- `school_ai_settings` — 15 columns
- `school_days_v2` — 10 columns
- `school_fee_summary` — 6 columns
- `school_staff_titles` — 4 columns
- `school_student_statuses` — 6 columns
- `signup_codes` — 18 columns
- `signups` — 13 columns
- `staff_documents` — 10 columns
- `student_ai_consent` — 14 columns
- `student_ai_consent_events` — 14 columns
- `subject_room_requirements_v2` — 10 columns
- `subscription_plans` — 12 columns
- `sync_changes` — 17 columns
- `sync_conflicts` — 20 columns
- `sync_log` — 11 columns
- `sync_tombstones` — 5 columns
- `teacher_availability_v2` — 13 columns
- `teacher_timetable_preferences_v2` — 12 columns
- `teacher_workload_profiles_v2` — 12 columns
- `timetable_approvals_v2` — 15 columns
- `timetable_audit_v2` — 14 columns
- `timetable_configurations_v2` — 19 columns
- `timetable_conflicts_v2` — 16 columns
- `timetable_entries` — 12 columns
- `timetable_entries_v2` — 18 columns
- `timetable_periods` — 11 columns
- `timetable_rooms_v2` — 13 columns
- `timetable_types_v2` — 10 columns
- `timetable_versions_v2` — 23 columns
- `ui_preferences` — 6 columns

## Limitations

- Static DDL/source comparison only; this does not prove runtime catalog parity.
- No live PostgreSQL database was queried or migrated.
- Foreign-key, index and trigger parity remain separate work items.

## Safety boundary

Migration 155 adds only standalone PostgreSQL DDL and tests. SQLite startup, SQLite migrations, application database selection, offline storage and offline synchronization are unchanged.
