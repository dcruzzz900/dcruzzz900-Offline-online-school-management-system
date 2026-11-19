# Modern Screens v106 → school-result-system v111 UI Port

## What was done

1. **Design system**
   - Added `static/css/modern.css` (full design tokens, shell, cards, KPIs, tables, forms from the v106 Complete Map).
   - Added `static/js/modern-shell.js` (hamburger / off-canvas sidebar behaviour matching the prototypes).
   - Linked both from `templates/base.html` (modern.css loads after shell-modern.css so it can refine the V105 shell).

2. **Login (01-login.html → login.html)**
   - Redesigned to the exact modern card layout (gradient header, circular logo, Inter, soft background gradients, rounded form controls).
   - **All v111 functionality preserved**:
     - CSRF, username/email/phone/admission/register, password
     - First-time student Class Login Code (collapsible)
     - Optional School ID / Tenant ID
     - Forgot password → account_recovery
     - Activate School
     - New School Signup / Staff Signup / Parent Signup links
     - Flash messages
     - School branding (logo + name) when available

3. **Mapping (modern screen → real template)**

| Modern screen | v111 template / route | Notes |
|---------------|----------------------|-------|
| 01-login | login.html | Done (modern card) |
| 02-admin-dashboard | admin_dashboard.html | Structure already close; modern.css applies KPI/card polish |
| 03-result-sheet | result.html / _result_sheet.html | Keep data/logic; apply modern result card classes |
| 04-parent-dashboard | parent_dashboard.html | |
| 05-teacher-score-entry | score_entry.html | |
| 06-broadsheet | broadsheet.html | |
| 07-classes | admin_classes.html | |
| 08-students | admin_students.html | |
| 09-teachers | admin_teachers.html | |
| 10-subjects | admin_subjects.html | |
| 11-parents | admin_parents.html | |
| 12-timetable | timetable_class_v2.html | |
| 13-grading | admin_grading.html | |
| 14-promote | admin_promote.html | |
| 15-analytics | admin_analytics.html | |
| 16-teacher-dashboard | teacher_dashboard.html | |
| 17-student-dashboard | student_dashboard.html | |
| 18-result-workflow | result_workflow.html | |
| 19-attendance | roll_call.html | |
| 20-materials | materials.html | |
| 21-notifications | notifications_inbox.html | |
| 22-billing | school_billing_portal.html | |
| 23-announcements | admin_announcements.html | |
| 24-ai-assistant | ai_result_assistant.html | |
| 25-ai-comments | ai_comments.html | |
| 26-ai-tutor | ai_tutor.html | |
| 27-theme-branding | theme_branding / admin theme | |
| 28-cumulative-result | cumulative_result.html | |
| 29-staff-attendance | staff_attendance.html | |
| 30-settings | settings_hub.html | |
| 31-register | register.html | |
| 32-recover | account_recovery.html | |
| 33-sessions-terms | admin_terms.html | |
| 34-assign-subjects | admin_class_subjects.html | |
| 35-class-roster | my_class_roster.html | |
| 36-parent-result | parent_result.html | |
| 37-score-history | score_history*.html | |
| 38-timetable-hub | timetable_hub / timetable_setup_v2 | |
| 39-change-password | change_password.html | |
| 40-signup-codes | admin_signup_codes.html | |
| 41-roles | admin_roles.html | |
| 42-activities | activities_list.html | |
| 43–45 parent/student portals | parent_* / student_* | |
| 46-messages | teacher_parent_messages.html | |
| 47/55 platform | platform_hub.html, platform_schools.html | |
| 48-school-profile | admin_school.html / admin_school_info.html | |
| 53-class-results | class_results_list.html / classes_list.html | |
| 54-ai-command-center | ai_command_center.html | |
| 56–57 platform billing | platform_billing*.html | |
| 61-result-settings | result_display_settings / related | |
| 76-setup-wizard | admin_setup_wizard.html | |
| 79-result-permissions | result_permissions.html | |
| 80-audit-history | admin_audit_history.html | |
| 81-result-fields | admin_result_fields.html | |
| 82-reports-hub | reports_hub / reports_analytics | |
| 86-registrar | registrar_dashboard.html | |
| 87-parent-verification | admin_parent_links.html | |
| 89-school-fees | school fees screens | |
| m01–m05 mobile | responsive rules already in modern.css + shell | |

## What is still recommended (next iterations)

- Walk remaining list templates (students, teachers, classes, subjects, parents, etc.) and replace table/header markup with the modern `.card` + `.panel-header` + `.data` patterns from the corresponding v106 HTML while keeping every form field and action.
- Align sidebar class names (`app-sidebar` ↔ `sidebar`) if you want the pure modern drawer classes; current CSS supports both via the existing shell-modern + modern cascade.
- Apply the same treatment to parent and student shells (they use separate top navs in base.html).
- Keep the full Modern Screens zip as a living style guide; open any `NN-*.html` side-by-side with the real template while porting.

## Branding note

Sample branding in the prototypes is **Government Secondary School, Gonin-Gora, Chikun, Kaduna**. The live system continues to use each school’s real name, logo, and theme colours from Settings / Theme & Branding.
