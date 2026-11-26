# PostgreSQL Trigger Porting Plan

> Review inventory generated from the effective v113 SQLite schema. This is not executable PostgreSQL trigger SQL.

**Total triggers:** 158

## Categories

| Category | Count |
|---|---:|
| `audit_or_history_capture` | 2 |
| `business_rule_or_other` | 2 |
| `cross_row_uniqueness` | 5 |
| `immutability_guard` | 30 |
| `offline_sync_timestamp` | 72 |
| `soft_delete_or_sync_tombstone` | 18 |
| `tenant_scope_propagation` | 29 |

## Trigger-by-trigger review

| Trigger | Table | Category | Timing | Event | OLD | NEW | RAISE(ABORT) |
|---|---|---|---|---|---:|---:|---:|
| `trg_ai_audit_log_tenant_stamp` | `ai_audit_log` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_ai_outputs_tenant_stamp` | `ai_outputs` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_attendance_audit_no_delete` | `attendance_audit` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_attendance_audit_no_update` | `attendance_audit` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_attendance_records_server_ts_immutable` | `attendance_records` | `immutability_guard` | BEFORE | UPDATE | yes | yes | yes |
| `trg_attendance_records_sync_defaults` | `attendance_records` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_attendance_records_sync_touch` | `attendance_records` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_attendance_records_tombstone` | `attendance_records` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_audit_log_no_delete` | `audit_log` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_audit_log_no_update` | `audit_log` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_billing_financial_audit_no_delete` | `billing_financial_audit` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_billing_financial_audit_no_update` | `billing_financial_audit` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_billing_payment_history_no_delete` | `billing_payment_history` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_billing_payment_history_no_update` | `billing_payment_history` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_billing_payment_insert_history` | `billing_payments` | `audit_or_history_capture` | AFTER | INSERT | no | yes | no |
| `trg_billing_payment_update_history` | `billing_payments` | `audit_or_history_capture` | AFTER | UPDATE | yes | yes | no |
| `trg_billing_report_downloads_no_delete` | `billing_report_downloads` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_billing_report_downloads_no_update` | `billing_report_downloads` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_class_subject_requirements_v2_sync_defaults` | `class_subject_requirements_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_class_subject_requirements_v2_sync_touch` | `class_subject_requirements_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_class_subjects_sync_defaults` | `class_subjects` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_class_subjects_sync_touch` | `class_subjects` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_class_subjects_tombstone` | `class_subjects` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_class_timetable_preferences_v2_sync_defaults` | `class_timetable_preferences_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_class_timetable_preferences_v2_sync_touch` | `class_timetable_preferences_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_classes_sync_defaults` | `classes` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_classes_sync_touch` | `classes` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_classes_tenant_stamp` | `classes` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_classes_tombstone` | `classes` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_deferred_actions_tenant_stamp` | `deferred_actions` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_device_credentials_tenant_stamp` | `device_credentials` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_enrollments_sync_defaults` | `enrollments` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_enrollments_sync_touch` | `enrollments` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_enrollments_tenant_stamp` | `enrollments` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_enrollments_tombstone` | `enrollments` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_fixed_activities_v2_sync_defaults` | `fixed_activities_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_fixed_activities_v2_sync_touch` | `fixed_activities_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_grade_scale_sync_defaults` | `grade_scale` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_grade_scale_sync_touch` | `grade_scale` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_grade_scale_tenant_stamp` | `grade_scale` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_grade_scale_tombstone` | `grade_scale` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_grading_config_sync_defaults` | `grading_config` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_grading_config_sync_touch` | `grading_config` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_grading_config_tenant_stamp` | `grading_config` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_grading_config_tombstone` | `grading_config` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_materials_sync_defaults` | `materials` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_materials_sync_touch` | `materials` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_materials_tenant_stamp` | `materials` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_materials_tombstone` | `materials` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_notifications_tenant_stamp` | `notifications` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_parent_accounts_tenant_stamp` | `parent_accounts` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_parent_consent_events_tenant_stamp` | `parent_consent_events` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_parent_students_tenant_stamp` | `parent_students` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_parent_teacher_messages_tenant_stamp` | `parent_teacher_messages` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_rbac_audit_log_no_delete` | `rbac_audit_log` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_rbac_audit_log_no_update` | `rbac_audit_log` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_result_publication_audit_no_delete` | `result_publication_audit` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_result_publication_audit_no_update` | `result_publication_audit` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_role_assignment_audit_no_delete` | `role_assignment_audit` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_role_assignment_audit_no_update` | `role_assignment_audit` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_role_assignments_tenant_stamp` | `role_assignments` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_schedule_slots_sync_defaults` | `schedule_slots` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_schedule_slots_sync_touch` | `schedule_slots` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_schedule_templates_sync_defaults` | `schedule_templates` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_schedule_templates_sync_touch` | `schedule_templates` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_school_ai_settings_tenant_stamp` | `school_ai_settings` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_school_days_v2_sync_defaults` | `school_days_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_school_days_v2_sync_touch` | `school_days_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_schools_school_code_permanent` | `schools` | `business_rule_or_other` | BEFORE | UPDATE | yes | yes | yes |
| `trg_score_audit_no_delete` | `score_audit` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_score_audit_no_update` | `score_audit` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_score_history_tenant_stamp` | `score_history` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_scores_sync_defaults` | `scores` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_scores_sync_touch` | `scores` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_scores_tenant_stamp` | `scores` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_scores_tombstone` | `scores` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_security_events_no_delete` | `security_events` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_security_events_no_update` | `security_events` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_sessions_sync_defaults` | `sessions` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_sessions_sync_touch` | `sessions` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_sessions_tenant_stamp` | `sessions` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_sessions_tombstone` | `sessions` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_staff_attendance_server_ts_immutable` | `staff_attendance` | `immutability_guard` | BEFORE | UPDATE | yes | yes | yes |
| `trg_staff_attendance_sync_defaults` | `staff_attendance` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_staff_attendance_sync_touch` | `staff_attendance` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_staff_attendance_tenant_stamp` | `staff_attendance` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_staff_attendance_tombstone` | `staff_attendance` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_staff_name_history_no_delete` | `staff_name_history` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_staff_name_history_no_update` | `staff_name_history` | `immutability_guard` | BEFORE | UPDATE | yes | yes | yes |
| `trg_student_ai_consent_events_no_delete` | `student_ai_consent_events` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_student_ai_consent_events_no_update` | `student_ai_consent_events` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_student_ai_consent_tenant_stamp` | `student_ai_consent` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_student_skill_ratings_sync_defaults` | `student_skill_ratings` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_student_skill_ratings_sync_touch` | `student_skill_ratings` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_student_skill_ratings_tombstone` | `student_skill_ratings` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_student_status_history_no_delete` | `student_status_history` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_student_status_history_no_update` | `student_status_history` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_student_term_info_sync_defaults` | `student_term_info` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_student_term_info_sync_touch` | `student_term_info` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_student_term_info_tombstone` | `student_term_info` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_students_admission_unique_ins` | `students` | `cross_row_uniqueness` | BEFORE | INSERT | no | yes | yes |
| `trg_students_admission_unique_upd` | `students` | `cross_row_uniqueness` | BEFORE | UPDATE | yes | yes | yes |
| `trg_students_stamp_tenant` | `students` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_students_sync_defaults` | `students` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_students_sync_touch` | `students` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_students_tenant_stamp` | `students` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_students_tombstone` | `students` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_subject_room_requirements_v2_sync_defaults` | `subject_room_requirements_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_subject_room_requirements_v2_sync_touch` | `subject_room_requirements_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_subjects_sync_defaults` | `subjects` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_subjects_sync_touch` | `subjects` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_subjects_tenant_stamp` | `subjects` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_subjects_tombstone` | `subjects` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_subscription_history_no_delete` | `subscription_history` | `immutability_guard` | BEFORE | DELETE | no | no | yes |
| `trg_subscription_history_no_update` | `subscription_history` | `immutability_guard` | BEFORE | UPDATE | no | no | yes |
| `trg_sync_conflicts_tenant_stamp` | `sync_conflicts` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_sync_log_tenant_stamp` | `sync_log` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_teacher_availability_v2_sync_defaults` | `teacher_availability_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_teacher_availability_v2_sync_touch` | `teacher_availability_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_teacher_timetable_preferences_v2_sync_defaults` | `teacher_timetable_preferences_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_teacher_timetable_preferences_v2_sync_touch` | `teacher_timetable_preferences_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_teacher_workload_profiles_v2_sync_defaults` | `teacher_workload_profiles_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_teacher_workload_profiles_v2_sync_touch` | `teacher_workload_profiles_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_terms_sync_defaults` | `terms` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_terms_sync_touch` | `terms` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_terms_tombstone` | `terms` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_timetable_approvals_v2_sync_defaults` | `timetable_approvals_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_approvals_v2_sync_touch` | `timetable_approvals_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_audit_v2_sync_defaults` | `timetable_audit_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_audit_v2_sync_touch` | `timetable_audit_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_configurations_v2_sync_defaults` | `timetable_configurations_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_configurations_v2_sync_touch` | `timetable_configurations_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_conflicts_v2_sync_defaults` | `timetable_conflicts_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_conflicts_v2_sync_touch` | `timetable_conflicts_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_entries_sync_defaults` | `timetable_entries` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_entries_sync_touch` | `timetable_entries` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_entries_tenant_stamp` | `timetable_entries` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_timetable_entries_tombstone` | `timetable_entries` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_timetable_entries_v2_sync_defaults` | `timetable_entries_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_entries_v2_sync_touch` | `timetable_entries_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_periods_sync_defaults` | `timetable_periods` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_periods_sync_touch` | `timetable_periods` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_periods_tenant_stamp` | `timetable_periods` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_timetable_periods_tombstone` | `timetable_periods` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |
| `trg_timetable_rooms_v2_sync_defaults` | `timetable_rooms_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_rooms_v2_sync_touch` | `timetable_rooms_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_types_v2_sync_defaults` | `timetable_types_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_types_v2_sync_touch` | `timetable_types_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_timetable_versions_v2_sync_defaults` | `timetable_versions_v2` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_timetable_versions_v2_sync_touch` | `timetable_versions_v2` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_users_identity_unique_ins` | `users` | `cross_row_uniqueness` | BEFORE | INSERT | no | yes | yes |
| `trg_users_identity_unique_upd` | `users` | `cross_row_uniqueness` | BEFORE | UPDATE | yes | yes | yes |
| `trg_users_signup_name_init` | `users` | `business_rule_or_other` | AFTER | INSERT | no | yes | no |
| `trg_users_signup_name_lock` | `users` | `cross_row_uniqueness` | BEFORE | UPDATE | yes | yes | yes |
| `trg_users_sync_defaults` | `users` | `offline_sync_timestamp` | AFTER | INSERT | no | yes | no |
| `trg_users_sync_touch` | `users` | `offline_sync_timestamp` | AFTER | UPDATE | yes | yes | no |
| `trg_users_tenant_stamp` | `users` | `tenant_scope_propagation` | AFTER | INSERT | no | yes | no |
| `trg_users_tombstone` | `users` | `soft_delete_or_sync_tombstone` | AFTER | DELETE | yes | no | no |

## Conversion rules

- Convert each trigger into a PostgreSQL PL/pgSQL function plus a trigger declaration.
- Replace SQLite `RAISE(ABORT, ...)` with an appropriate PostgreSQL exception (`RAISE EXCEPTION`) and preserve user-facing error meaning.
- Re-evaluate `IS` / `IS NOT` comparisons, empty-string checks, and NULL handling under PostgreSQL semantics.
- Review `AFTER` triggers that update the same row; prefer `BEFORE` triggers that assign `NEW.column` where equivalent and safe.
- Ensure tenant stamping cannot infer a tenant from an ambiguous parent row; enforce tenant consistency with constraints and explicit application context.
- Preserve tombstone and audit/history behaviour, including append-only guarantees.
- Add integration tests for every trigger before production cutover.

**Do not apply this inventory as SQL.** Trigger bodies remain unconverted until reviewed and tested against PostgreSQL.
