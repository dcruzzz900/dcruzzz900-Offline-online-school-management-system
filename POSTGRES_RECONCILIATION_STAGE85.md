# Stage 85 — PostgreSQL schema reconciliation after Migration 156

| Measure | Current static result |
|---|---:|
| Source SQLite tables | 113 |
| Explicit PostgreSQL table definitions | 81 |
| Unresolved table candidates | 32 |
| Columns in unresolved candidates | 396 |
| Unresolved foreign-key declarations | 35 |
| Unresolved indexes | 47 |
| Registered PostgreSQL migrations | 57 (100–156) |

## Migration 156

`signup_codes` is now explicitly created by the standalone PostgreSQL migration. Its effective 18-column shape includes the later-added `session_id` and `class_arm` fields. The migration preserves unique code values, both source CHECK domains, the school foreign key, and the `(school_id, code_type, status)` index.

## Remaining table candidates

- `schedule_slots` — 20 columns; 3 foreign-key declarations; 1 indexes
- `schedule_templates` — 13 columns; 3 foreign-key declarations; 1 indexes
- `schema_steps` — 2 columns; 0 foreign-key declarations; 1 indexes
- `school_ai_settings` — 15 columns; 0 foreign-key declarations; 0 indexes
- `school_days_v2` — 10 columns; 1 foreign-key declarations; 2 indexes
- `school_fee_summary` — 6 columns; 0 foreign-key declarations; 1 indexes
- `school_staff_titles` — 4 columns; 0 foreign-key declarations; 1 indexes
- `school_student_statuses` — 6 columns; 0 foreign-key declarations; 1 indexes
- `signups` — 13 columns; 2 foreign-key declarations; 1 indexes
- `staff_documents` — 10 columns; 0 foreign-key declarations; 2 indexes
- `student_ai_consent` — 14 columns; 0 foreign-key declarations; 1 indexes
- `student_ai_consent_events` — 14 columns; 0 foreign-key declarations; 1 indexes
- `subject_room_requirements_v2` — 10 columns; 3 foreign-key declarations; 2 indexes
- `subscription_plans` — 12 columns; 0 foreign-key declarations; 2 indexes
- `sync_changes` — 17 columns; 0 foreign-key declarations; 2 indexes
- `sync_conflicts` — 20 columns; 1 foreign-key declarations; 2 indexes
- `sync_log` — 11 columns; 0 foreign-key declarations; 1 indexes
- `sync_tombstones` — 5 columns; 0 foreign-key declarations; 1 indexes
- `teacher_availability_v2` — 13 columns; 4 foreign-key declarations; 2 indexes
- `teacher_timetable_preferences_v2` — 12 columns; 2 foreign-key declarations; 1 indexes
- `teacher_workload_profiles_v2` — 12 columns; 2 foreign-key declarations; 2 indexes
- `timetable_approvals_v2` — 15 columns; 1 foreign-key declarations; 1 indexes
- `timetable_audit_v2` — 14 columns; 1 foreign-key declarations; 1 indexes
- `timetable_configurations_v2` — 19 columns; 0 foreign-key declarations; 2 indexes
- `timetable_conflicts_v2` — 16 columns; 1 foreign-key declarations; 1 indexes
- `timetable_entries` — 12 columns; 5 foreign-key declarations; 3 indexes
- `timetable_entries_v2` — 18 columns; 2 foreign-key declarations; 2 indexes
- `timetable_periods` — 11 columns; 1 foreign-key declarations; 2 indexes
- `timetable_rooms_v2` — 13 columns; 1 foreign-key declarations; 2 indexes
- `timetable_types_v2` — 10 columns; 1 foreign-key declarations; 2 indexes
- `timetable_versions_v2` — 23 columns; 1 foreign-key declarations; 2 indexes
- `ui_preferences` — 6 columns; 0 foreign-key declarations; 1 indexes

## Limitations

- Static DDL/source comparison only; no live PostgreSQL catalog was queried.
- Explicit CREATE TABLE coverage does not prove column/default/constraint parity for the matched tables.
- Foreign-key, index and trigger parity remain separate work items.
- Application SQL compatibility and live PostgreSQL execution have not been tested.

## Safety boundary

Migration 156 is standalone PostgreSQL DDL. It does not switch application database selection, change SQLite startup or migrations, or alter offline storage/synchronization.
