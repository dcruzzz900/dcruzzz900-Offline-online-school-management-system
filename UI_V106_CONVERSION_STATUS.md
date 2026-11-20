# V112 – v106 → v111 conversion tracker

Goal: every screen uses the exact v106 markup/CSS (`modern.css`) with live v111 data and forms. A converted template sets `{% set v106_page = true %}`, which stops legacy v111 CSS loading on that page so nothing leaks in.

**Screens: 91 in v106. Converted: 3. Remaining: 88.**

| v106 screen | v111 template | status |
|---|---|---|
| 00-role-menus | ? | styled via shared layer only – NOT yet converted |
| 01-login | login | styled via shared layer only – NOT yet converted |
| 02-admin-dashboard | admin_dashboard | EXACT v106 markup + live data (done) |
| 03-result-sheet | result / _result_sheet | styled via shared layer only – NOT yet converted |
| 04-parent-dashboard | parent_dashboard | styled via shared layer only – NOT yet converted |
| 05-teacher-score-entry | score_entry | styled via shared layer only – NOT yet converted |
| 06-broadsheet | broadsheet | styled via shared layer only – NOT yet converted |
| 07-classes | admin_classes | styled via shared layer only – NOT yet converted |
| 08-students | admin_students | styled via shared layer only – NOT yet converted |
| 09-teachers | admin_teachers | styled via shared layer only – NOT yet converted |
| 10-subjects | admin_subjects | styled via shared layer only – NOT yet converted |
| 11-parents | admin_parents | styled via shared layer only – NOT yet converted |
| 12-timetable | timetable_hub | styled via shared layer only – NOT yet converted |
| 13-grading | admin_grading | styled via shared layer only – NOT yet converted |
| 14-promote | admin_promote | styled via shared layer only – NOT yet converted |
| 15-analytics | admin_analytics | styled via shared layer only – NOT yet converted |
| 16-teacher-dashboard | teacher_dashboard | styled via shared layer only – NOT yet converted |
| 17-student-dashboard | student_dashboard | styled via shared layer only – NOT yet converted |
| 18-result-workflow | result_workflow | styled via shared layer only – NOT yet converted |
| 19-attendance | roll_call | styled via shared layer only – NOT yet converted |
| 20-materials | materials | styled via shared layer only – NOT yet converted |
| 21-notifications | notifications_inbox | styled via shared layer only – NOT yet converted |
| 22-billing | school_billing_portal | styled via shared layer only – NOT yet converted |
| 23-announcements | admin_announcements | styled via shared layer only – NOT yet converted |
| 24-ai-assistant | ai_result_assistant | styled via shared layer only – NOT yet converted |
| 25-ai-comments | ai_comments | styled via shared layer only – NOT yet converted |
| 26-ai-tutor | ai_tutor | styled via shared layer only – NOT yet converted |
| 27-theme-branding | theme_branding | styled via shared layer only – NOT yet converted |
| 28-cumulative-result | cumulative_result | styled via shared layer only – NOT yet converted |
| 29-staff-attendance | staff_attendance | styled via shared layer only – NOT yet converted |
| 30-settings | settings_hub | styled via shared layer only – NOT yet converted |
| 31-register | register | styled via shared layer only – NOT yet converted |
| 32-recover | recover | styled via shared layer only – NOT yet converted |
| 33-sessions-terms | admin_terms | styled via shared layer only – NOT yet converted |
| 34-assign-subjects | admin_class_subjects | styled via shared layer only – NOT yet converted |
| 35-class-roster | class_register / my_class_roster | styled via shared layer only – NOT yet converted |
| 36-parent-result | parent_result | styled via shared layer only – NOT yet converted |
| 37-score-history | score_history | styled via shared layer only – NOT yet converted |
| 38-timetable-hub | timetable_hub | styled via shared layer only – NOT yet converted |
| 39-change-password | change_password | v106-style card (centred); legacy CSS still loads |
| 40-signup-codes | admin_signup_codes | styled via shared layer only – NOT yet converted |
| 41-roles | admin_roles / staff_roles | styled via shared layer only – NOT yet converted |
| 42-activities | activities_list | styled via shared layer only – NOT yet converted |
| 43-parent-children | parent_children | styled via shared layer only – NOT yet converted |
| 44-parent-attendance | parent_attendance | styled via shared layer only – NOT yet converted |
| 45-student-result | student_result | styled via shared layer only – NOT yet converted |
| 46-messages | teacher_parent_messages | styled via shared layer only – NOT yet converted |
| 47-platform-hub | platform_hub | styled via shared layer only – NOT yet converted |
| 48-school-profile | admin_school | styled via shared layer only – NOT yet converted |
| 49-parent-timetable | parent_timetable | styled via shared layer only – NOT yet converted |
| 50-parent-contact | parent_contact_school | styled via shared layer only – NOT yet converted |
| 51-student-timetable | student_timetable | styled via shared layer only – NOT yet converted |
| 52-staff-profile | staff_profile | styled via shared layer only – NOT yet converted |
| 53-class-results | class_results_list | styled via shared layer only – NOT yet converted |
| 54-ai-command-center | ai_command_center | styled via shared layer only – NOT yet converted |
| 55-platform-hub | platform_hub | styled via shared layer only – NOT yet converted |
| 55-platform-schools | platform_schools | styled via shared layer only – NOT yet converted |
| 56-platform-billing | platform_billing | styled via shared layer only – NOT yet converted |
| 57-platform-subscriptions | platform_subscriptions | styled via shared layer only – NOT yet converted |
| 58-register-parent | register_parent | styled via shared layer only – NOT yet converted |
| 59-student-profile | student_profile | styled via shared layer only – NOT yet converted |
| 60-ai-alerts | ai_alerts | styled via shared layer only – NOT yet converted |
| 61-result-settings | result_display_settings | styled via shared layer only – NOT yet converted |
| 62-attendance-history | roll_call_history | styled via shared layer only – NOT yet converted |
| 63-parent-profile | parent_profile_self | styled via shared layer only – NOT yet converted |
| 64-register-school | register_school | styled via shared layer only – NOT yet converted |
| 65-staff-onboarding | staff_onboarding | styled via shared layer only – NOT yet converted |
| 66-notifications-compose | notifications_compose | styled via shared layer only – NOT yet converted |
| 67-ai-consent | ai_consent | styled via shared layer only – NOT yet converted |
| 68-ai-privacy | ai_privacy | styled via shared layer only – NOT yet converted |
| 69-student-materials | student_materials | styled via shared layer only – NOT yet converted |
| 70-class-login-codes | class_login_codes | styled via shared layer only – NOT yet converted |
| 71-ai-result-analysis | ai_result_analysis | styled via shared layer only – NOT yet converted |
| 72-search-results | search_results | styled via shared layer only – NOT yet converted |
| 73-admin-email | admin_email | styled via shared layer only – NOT yet converted |
| 74-student-login | student_login | styled via shared layer only – NOT yet converted |
| 75-billing-receipt | school_billing_receipt | styled via shared layer only – NOT yet converted |
| 76-setup-wizard | admin_setup_wizard | styled via shared layer only – NOT yet converted |
| 77-subadmins | admin_subadmins | styled via shared layer only – NOT yet converted |
| 78-custom-fields | admin_custom_fields | styled via shared layer only – NOT yet converted |
| 79-result-permissions | result_permissions | styled via shared layer only – NOT yet converted |
| 80-audit-history | admin_audit_history | styled via shared layer only – NOT yet converted |
| 81-result-fields | admin_result_fields | styled via shared layer only – NOT yet converted |
| 82-reports-hub | reports_hub | styled via shared layer only – NOT yet converted |
| 83-parent-link-child | parent_link_child | styled via shared layer only – NOT yet converted |
| 84-admin-domains | admin_domains | styled via shared layer only – NOT yet converted |
| 85-terminal-results-list | class_results_list | styled via shared layer only – NOT yet converted |
| 86-registrar-dashboard | registrar_dashboard | styled via shared layer only – NOT yet converted |
| 87-parent-verification | admin_parent_links | styled via shared layer only – NOT yet converted |
| 88-custom-school-info | admin_school_info | styled via shared layer only – NOT yet converted |
| 89-school-fees | admin_school_fees  (NEW in v112) | v106-style page, summary data only (done, v111 has no invoice ledger) |

## v111 templates with no v106 screen (functionality to keep and restyle in v106 language)

77 templates:

account_recovery, account_recovery_reset, activate, admin_custom_field_detail, admin_custom_field_form, admin_data_completion, admin_first_login, admin_parent_detail, ai_learning_materials, ai_output, broadsheet_print, classes_list, cumulative_broadsheet, cumulative_result_print, my_attendance_picker, my_class_picker, parent_ai_consent, parent_child_detail, parent_cumulative_result, parent_message_thread, parent_notifications, parent_profile, platform_activation_requests, platform_audit, platform_backups, platform_billing_adjustments, platform_billing_analytics, platform_billing_audit, platform_billing_fraud_controls, platform_billing_net_revenue, platform_billing_operations, platform_billing_reconciliation, platform_billing_recovery, platform_billing_reports, platform_billing_security_review, platform_control_center, platform_custom_fields, platform_dashboard, platform_login, platform_new_school, platform_notification_inbox, platform_notifications, platform_plans, platform_role_form, platform_roles, platform_school_billing, platform_school_provisioning, platform_school_subscription, platform_school_verification, platform_security_audit, platform_subscription_history, platform_subscription_manager, platform_users, platform_v47_readiness, profile_denied, profile_form, recover_answer, recover_reset, reports_analytics, result_blocked, result_preview, result_print, result_workflow_history, score_history_all, staff_attendance_history, student_account, student_attendance, student_cumulative_result, student_status_history, student_subjects, teacher_parent_thread, timetable_class_v2, timetable_edit_v2, timetable_generate_v2, timetable_setup_v2, timetable_teacher_v2, timetable_version_v2
