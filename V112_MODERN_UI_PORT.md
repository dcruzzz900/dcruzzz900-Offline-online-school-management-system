# V112 - Modern Screens v106 port

Base: school-result-system-v111. Reference: *Modern Screens - v106 Complete Map* (96 screens).

## What changed
* `static/css/modern-v106.css` (new, loaded last): v106 design tokens and components re-skinning the real markup - cards, tables with coloured header, buttons, forms, badges, KPI tiles, auth screens, student/parent/platform top navs. It follows the school's Theme & Branding colours and works in light and dark mode. Print output is untouched.
* **Shell (v106 `shell.js`)**: the sidebar is one off-canvas drawer at every screen width, with hamburger, backdrop, Esc and tap-outside close, scroll lock, and the current page highlighted (`static/js/shell-ui.js`). Topbar has the pill search, notifications bell, role chip and avatar.
* **Role menus (v106 `00-role-menus`)**: added Sub-Admins, School Information (school profile), Result Display, Custom School Info, Email Settings, AI Comments (teacher), student Timetable, parent Contact School.
* **Students page** restructured to the v106 layout (see table).
* `tests/v75_scenarios.py`: the old assertion "desktop shows the sidebar with no hamburger" now asserts the v106 drawer behaviour.

## Not changed on purpose
No routes, forms, field names, CSRF tokens, Jinja bindings, database code or permissions were changed. The v106 mock screens are static and simpler than the live pages (e.g. the real sign-in has class-code and school-ID fields), so they were used as a visual reference, not copied over.

## Still to do (next phases)
* Page-by-page structural redesign of the remaining screens (they already have the v106 look through the design layer).
* **School Fees screen (89)**: the app only stores totals (`school_fee_summary`); the mock's payments table needs a new payments table and forms.
* Phone-shell mock screens (m01-m05) - the existing mobile tab bar was kept and restyled.

## Screen map
| Mock screen | Title | v111 template(s) | Status |
|---|---|---|---|
| 00-role-menus.html | Menus by Role | `base.html nav` | n/a |
| 01-login.html | Login | `login.html` | Design layer (gradient hero, curved edge, rounded inputs); v111 unified login kept (class code, school ID, 3 signup paths) |
| 02-admin-dashboard.html | Admin Dashboard | `admin_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 03-result-sheet.html | Terminal Result | `result.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 04-parent-dashboard.html | Parent Dashboard | `parent_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 05-teacher-score-entry.html | Score Entry | `score_entry.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 06-broadsheet.html | Broadsheet | `broadsheet.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 07-classes.html | Classes | `admin_classes.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 08-students.html | Students | `admin_students.html` | Page restructured (header, KPI tiles, collapsible add/upload, directory table) |
| 09-teachers.html | Teachers | `admin_teachers.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 10-subjects.html | Subjects | `admin_subjects.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 11-parents.html | Parents | `admin_parents.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 12-timetable.html | Class Timetable | `timetable_class_v2.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 13-grading.html | Grading Setup | `admin_grading.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 14-promote.html | Promote Students | `admin_promote.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 15-analytics.html | Analytics | `admin_analytics.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 16-teacher-dashboard.html | Teacher Dashboard | `teacher_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 17-student-dashboard.html | Student Portal | `student_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 18-result-workflow.html | Result Approval | `result_workflow.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 19-attendance.html | Student Attendance | `roll_call.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 20-materials.html | Learning Materials | `materials.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 21-notifications.html | Notifications | `notifications_inbox.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 22-billing.html | Billing Portal | `school_billing_portal.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 23-announcements.html | Announcements | `admin_announcements.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 24-ai-assistant.html | AI Result Assistant | `ai_result_assistant.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 25-ai-comments.html | AI Comments | `ai_comments.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 26-ai-tutor.html | AI Tutor | `ai_tutor.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 27-theme-branding.html | Themes & Branding | `theme_branding.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 28-cumulative-result.html | Cumulative Result | `cumulative_result.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 29-staff-attendance.html | Staff Attendance | `staff_attendance.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 30-settings.html | Settings Hub | `settings_hub.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 31-register.html | Staff Registration | `register.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 32-recover.html | Account Recovery | `recover.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 33-sessions-terms.html | Sessions & Terms | `admin_terms.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 34-assign-subjects.html | Assign Subjects | `admin_class_subjects.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 35-class-roster.html | Class Roster | `my_class_roster.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 36-parent-result.html | Child Result | `parent_result.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 37-score-history.html | Score History | `score_history.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 38-timetable-hub.html | Timetable Hub | `timetable_hub.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 39-change-password.html | Change Password | `change_password.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 40-signup-codes.html | Signup Codes | `admin_signup_codes.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 41-roles.html | Roles & Permissions | `admin_roles.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 42-activities.html | Activity Log | `activities_list.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 43-parent-children.html | My Children | `parent_children.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 44-parent-attendance.html | Child Attendance | `parent_attendance.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 45-student-result.html | My Result | `student_result.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 46-messages.html | Messages | `teacher_parent_messages.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 47-platform-hub.html | Platform Hub | `platform_hub.html / platform_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 48-school-profile.html | School Profile | `admin_school.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 49-parent-timetable.html | Parent Timetable | `parent_timetable.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 50-parent-contact.html | Contact School | `parent_contact_school.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 51-student-timetable.html | Student Timetable | `student_timetable.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 52-staff-profile.html | Staff Profile | `staff_profile.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 53-class-results.html | Class Results List | `class_results_list.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 54-ai-command-center.html | AI Command Center | `ai_command_center.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 55-platform-schools.html | Platform Schools | `platform_schools.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 56-platform-billing.html | Platform Billing | `platform_billing.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 57-platform-subscriptions.html | Subscriptions | `platform_subscriptions.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 58-register-parent.html | Parent Registration | `register_parent.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 59-student-profile.html | Student Profile | `student_profile.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 60-ai-alerts.html | AI Alerts | `ai_alerts.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 61-result-settings.html | Result Settings | `result_display_settings.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 62-attendance-history.html | Attendance History | `roll_call_history.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 63-parent-profile.html | Parent Profile | `parent_profile.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 64-register-school.html | Register School | `register_school.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 65-staff-onboarding.html | Staff Onboarding | `staff_onboarding.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 66-notifications-compose.html | Compose Notification | `notifications_compose.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 67-ai-consent.html | AI Consent | `ai_consent.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 68-ai-privacy.html | AI Privacy | `ai_privacy.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 69-student-materials.html | Student Materials | `student_materials.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 70-class-login-codes.html | Class Login Codes | `class_login_codes.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 71-ai-result-analysis.html | AI Result Analysis | `ai_result_analysis.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 72-search-results.html | Search Results | `search_results.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 73-admin-email.html | Email Settings | `admin_email.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 74-student-login.html | Student Login | `student_login.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 75-billing-receipt.html | Billing Receipt | `school_billing_receipt.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 76-setup-wizard.html | Setup Wizard | `admin_setup_wizard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 77-subadmins.html | Sub-Admins | `admin_subadmins.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 78-custom-fields.html | Custom Fields | `admin_custom_fields.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 79-result-permissions.html | Result Permissions | `result_permissions.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 80-audit-history.html | Audit History | `admin_audit_history.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 81-result-fields.html | Result Fields | `admin_result_fields.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 82-reports-hub.html | Reports Hub | `reports_hub.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 83-parent-link-child.html | Link Child | `parent_link_child.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 84-admin-domains.html | Email Domains | `admin_domains.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 85-terminal-results-list.html | Terminal Results List | `class_results_list.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 86-registrar-dashboard.html | Registrar | `registrar_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 87-parent-verification.html | Parent Verification | `admin_parent_links.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 89-school-fees.html | School Fees | `school fees (v105+)` | NEW - not built: needs backend |
| m01-admin-mobile.html | Admin Mobile | `phone shell` | n/a |
| m02-teacher-mobile.html | Teacher Mobile | `phone shell` | n/a |
| m03-parent-mobile.html | Parent Mobile | `phone shell` | n/a |
| m04-student-mobile.html | Student Mobile | `phone shell` | n/a |
| m05-analytics-mobile.html | Analytics Mobile | `phone shell` | n/a |
