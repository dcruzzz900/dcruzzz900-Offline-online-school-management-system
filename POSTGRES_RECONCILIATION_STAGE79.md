# Stage 79 — PostgreSQL Schema Reconciliation

## Source and scope

- Source archive: `school-result-system-v126-stage78-migration151.zip`
- Effective source schema: version 99
- Required tables: **113**
- Required columns: **1,569**
- Registered standalone PostgreSQL migrations: **52 (100–151)**
- Source foreign-key declarations: **125**
- Source explicit indexes: **148**
- Source SQLite triggers: **158**

## Initial static table-definition scan

- Required tables with an explicit `CREATE TABLE` match in `postgres_schema_base.sql` or `postgres_migration_*.py`: **76**
- Required tables without an explicit match (manual-review candidates): **37**

> Important: these 37 names are candidates, not confirmed missing PostgreSQL tables. The scan is textual and cannot reliably detect dynamically assembled DDL, helper-generated DDL, or objects supplied through another schema mechanism. No live PostgreSQL database was available for catalog inspection.

## Tables with explicit CREATE TABLE matches

- `activation_attempts` — postgres_migration_102_activation_attempts.py
- `activation_codes` — postgres_schema_base.sql
- `ai_audit_log` — postgres_migration_106_ai_audit_log.py
- `ai_outputs` — postgres_migration_107_ai_outputs.py
- `announcement_dismissals` — postgres_migration_108_announcement_dismissals.py
- `announcements` — postgres_migration_109_announcements.py
- `attendance_audit` — postgres_migration_110_attendance_audit.py
- `attendance_records` — postgres_schema_base.sql
- `audit_log` — postgres_schema_base.sql
- `billing_adjustments` — postgres_migration_117_billing_adjustments.py
- `billing_email_delivery` — postgres_migration_112_billing_email_delivery.py
- `billing_financial_audit` — postgres_migration_118_billing_financial_audit.py
- `billing_invoices` — postgres_migration_113_billing_invoices.py
- `billing_job_runs` — postgres_migration_111_billing_job_runs.py
- `billing_notification_events` — postgres_migration_114_billing_notification_events.py
- `billing_payment_history` — postgres_migration_116_billing_payment_history.py
- `billing_payments` — postgres_migration_115_billing_payments.py
- `billing_receipts` — postgres_migration_119_billing_receipts.py
- `billing_reconciliation_exceptions` — postgres_migration_120_billing_reconciliation_exceptions.py
- `billing_renewal_recovery` — postgres_migration_121_billing_renewal_recovery.py
- `billing_report_downloads` — postgres_migration_122_billing_report_downloads.py
- `billing_webhook_events` — postgres_migration_123_billing_webhook_events.py
- `change_audit` — postgres_migration_124_change_audit.py
- `class_login_codes` — postgres_migration_125_class_login_codes.py
- `class_subject_requirements_v2` — postgres_migration_127_class_subject_requirements_v2.py
- `class_subjects` — postgres_schema_base.sql
- `class_timetable_preferences_v2` — postgres_migration_128_class_timetable_preferences_v2.py
- `classes` — postgres_schema_base.sql
- `custom_field_options` — postgres_migration_126_custom_field_options.py
- `custom_field_values` — postgres_migration_130_custom_field_values.py
- `custom_fields` — postgres_migration_129_custom_fields.py
- `deferred_actions` — postgres_migration_131_deferred_actions.py
- `device_credentials` — postgres_migration_132_device_credentials.py
- `educational_domains` — postgres_migration_103_educational_domains.py
- `enrollments` — postgres_schema_base.sql
- `fixed_activities_v2` — postgres_migration_134_fixed_activities_v2.py
- `grade_scale` — postgres_schema_base.sql
- `grading_config` — postgres_schema_base.sql
- `grading_config_audit` — postgres_migration_135_grading_config_audit.py
- `materials` — postgres_schema_base.sql
- `notifications` — postgres_schema_base.sql
- `offline_sync_tokens` — postgres_migration_133_offline_sync_tokens.py
- `parent_accounts` — postgres_migration_136_parent_accounts.py
- `parent_consent_events` — postgres_migration_137_parent_consent_events.py
- `parent_students` — postgres_migration_138_parent_students.py
- `parent_teacher_messages` — postgres_migration_139_parent_teacher_messages.py
- `password_reset_tokens` — postgres_migration_140_password_reset_tokens.py
- `platform_activation_requests` — postgres_migration_141_platform_activation_requests.py
- `platform_admins` — postgres_schema_base.sql
- `platform_notifications` — postgres_migration_101_platform_notifications.py
- `rbac_audit_log` — postgres_migration_142_rbac_audit_log.py
- `result_publication` — postgres_migration_149_result_publication.py
- `result_publication_audit` — postgres_migration_150_result_publication_audit.py
- `result_workflow_permissions` — postgres_migration_151_result_workflow_permissions.py
- `role_assignment_audit` — postgres_migration_143_role_assignment_audit.py
- `role_assignment_permissions` — postgres_migration_145_role_assignment_permissions.py
- `role_assignments` — postgres_migration_144_role_assignments.py
- `schema_version` — postgres_schema_base.sql
- `schools` — postgres_schema_base.sql
- `score_audit` — postgres_migration_147_score_audit.py
- `score_history` — postgres_schema_base.sql
- `scores` — postgres_schema_base.sql
- `security_events` — postgres_migration_100_security_events.py
- `sessions` — postgres_schema_base.sql
- `skill_traits` — postgres_schema_base.sql
- `staff_attendance` — postgres_schema_base.sql
- `staff_name_history` — postgres_migration_146_staff_name_history.py
- `status_history` — postgres_migration_104_status_history.py
- `student_skill_ratings` — postgres_schema_base.sql
- `student_status_history` — postgres_migration_105_student_status_history.py
- `student_term_info` — postgres_schema_base.sql
- `students` — postgres_schema_base.sql
- `subjects` — postgres_schema_base.sql
- `subscription_history` — postgres_migration_148_subscription_history.py
- `terms` — postgres_schema_base.sql
- `users` — postgres_schema_base.sql

## Candidate tables requiring manual review

- `result_custom_fields`
- `result_custom_values`
- `result_display_settings`
- `schedule_slots`
- `schedule_templates`
- `schema_steps`
- `school_ai_settings`
- `school_custom_info`
- `school_days_v2`
- `school_fee_summary`
- `school_staff_titles`
- `school_student_statuses`
- `signup_codes`
- `signups`
- `staff_documents`
- `student_ai_consent`
- `student_ai_consent_events`
- `subject_room_requirements_v2`
- `subscription_plans`
- `sync_changes`
- `sync_conflicts`
- `sync_log`
- `sync_tombstones`
- `teacher_availability_v2`
- `teacher_timetable_preferences_v2`
- `teacher_workload_profiles_v2`
- `timetable_approvals_v2`
- `timetable_audit_v2`
- `timetable_configurations_v2`
- `timetable_conflicts_v2`
- `timetable_entries`
- `timetable_entries_v2`
- `timetable_periods`
- `timetable_rooms_v2`
- `timetable_types_v2`
- `timetable_versions_v2`
- `ui_preferences`

## Remaining reconciliation work

1. Trace each candidate table to its source definition and all PostgreSQL DDL/helper calls.
2. Compare all 1,569 required columns against PostgreSQL definitions, including type, nullability, defaults and generated/identity behaviour.
3. Compare all 125 foreign-key declarations and 148 explicit indexes.
4. Reconcile all 158 SQLite triggers into PostgreSQL-native functions/triggers or documented application-level equivalents.
5. Review the 82 flagged SQLite migration registry entries individually; flags do not imply one PostgreSQL migration per entry.
6. Run migration tests and, when a PostgreSQL test service is available, apply migrations to a disposable PostgreSQL database and inspect `pg_catalog`.
7. Run application integration tests against PostgreSQL separately from SQLite/offline tests.

## Safety boundary

This stage adds only reconciliation documentation and a reproducible static report. It does not change SQLite startup, SQLite migrations, offline storage, offline synchronization, application database selection, or the PostgreSQL migration registry. No Migration 152 is created in this stage. Live PostgreSQL execution remains untested.
