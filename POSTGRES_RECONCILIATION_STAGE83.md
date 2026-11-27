# Stage 83 — PostgreSQL schema reconciliation

This is a refreshed static comparison after Migration 154. It does not query a live PostgreSQL catalog.

| Measure | Current static result |
|---|---:|
| Source SQLite tables | 113 |
| Explicit PostgreSQL table definitions | 79 |
| Unresolved table candidates | 34 |
| Columns in unresolved candidates | 471 |
| Unresolved foreign-key declarations | 36 |
| Unresolved indexes | 49 |
| Registered PostgreSQL migrations | 55 |

## Unresolved table candidates

- `result_display_settings` — 57 columns
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

- Static DDL scan only; absence of explicit CREATE TABLE does not prove a table is not provisioned through another mechanism.
- Foreign-key and index totals are outstanding source declarations, not proof of runtime failure.
- Live PostgreSQL execution and catalog parity have not been tested.
