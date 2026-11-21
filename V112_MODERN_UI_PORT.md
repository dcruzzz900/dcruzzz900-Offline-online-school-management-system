# V112 - Modern Screens v106 port

Base: school-result-system-v111. Reference: *Modern Screens - v106 Complete Map* (96 screens).

## Pixel alignment pass (measured, not eyeballed)
`tools/v106_style_compare.py <mock folder>` opens a v106 mock screen and the matching live page at 1366x800 and prints every computed style that differs (size, weight, colour, padding, radius, shadow, font). After this pass these components match the mock exactly: top bar (62px), sidebar and drawer (gradient, brand block, status block), menu items and the active item, hamburger, table header and cells, primary and secondary buttons, text inputs, KPI tiles, badges and the page header. What still differs is content, not styling: widths that depend on the text or the number of tiles, and the card gap (the mock spaces cards with its own page flex).
* **Base text is 15px at 100%** (v106 `html{font-size:15px}`); v111 was 17px. The A- / A+ text-size control still scales it. **Typeface is Inter** (loaded from Google Fonts like the mock; offline it falls back to the system font).
* **Default brand colours are now v106's `#1a6fe8` / `#0a2a6b`** (were `#1f6feb` / `#0b3b75`). Schools still on the untouched old defaults are moved by migration `brand_defaults_v112`; any school that chose its own colours or another preset keeps them. `tests/v107_scenarios.py` now expects the new default after "Reset to default theme".
* **Round 2 pages matched to their mock**: Teachers & Staff (tiles, live search and status filter, badges, link actions), Subjects (adds Assigned Teachers and Classes counts), Parents, Announcements (cards with status edge and badge, Remove kept), Assign Subjects (class filter, flush table). The mock file `77-subadmins.html` in the supplied zip is empty (0 bytes), so Sub-Admins has no reference and keeps the shared v106 page header and table.
* **Round 3**: Grading Setup now has the mock's two-column layout (Score Weighting beside an editable Grade Scale table, grade bands added from a collapsible panel) plus the "Live preview of scale" bars drawn from the saved bands; the Notifications inbox is a v106 row list (icon tile, title, message, sender, unread dot, Compose in the header). A one-off script copied each v106 screen's page-header icon (and static subtitle) onto its matching page, so ~20 more pages now share the exact v106 header: Sessions & Terms, Promote Students, Signup Codes, Settings, Score Entry, Roll Call, Staff Attendance, Timetable, Materials, Billing, School Profile, Class Results, AI Command Center, Result Display, Custom Fields, Additional Result Fields, Audit History, Parent Verification. 7 more content checks were added to `tests/v112_scenarios.py` (32 total).
* **Pages matched to their mock layout** (header with icon, tiles, filter row, table card, text-link actions, v106 badges): Students (with live search, gender and status filters), Classes (adds Students and Subjects counts per class and total tiles; category and class-teacher editing, Broadsheet and Delete kept), plus the earlier Teachers, Subjects, Sub-Admins, Assign Subjects, Sessions & Terms, Announcements, Settings, Reports, Roll Call, Score Entry and School Fees.
* Status chips everywhere now use the v106 badge colours (the text stays, the duplicate emoji is hidden); the live clock sits in the top bar.

## Known gaps to the mock
Where the mock shows data or fields the app does not have, the live page cannot be pixel-identical without new features: a per-class Status column, "New this term" tile, per-row Edit pages. Pages not listed above still have their v111 layout in the v106 look; run the compare tool to see what differs on each.

## What changed
* `static/css/modern-v106.css` (new, loaded last): v106 design tokens and components re-skinning the real markup - cards, tables with coloured header, buttons, forms, badges, KPI tiles, auth screens, student/parent/platform top navs. It follows the school's Theme & Branding colours and works in light and dark mode. Print output is untouched.
* **Shell (v106 `shell.js`)**: the sidebar is one off-canvas drawer at every screen width, with hamburger, backdrop, Esc and tap-outside close, scroll lock, and the current page highlighted (`static/js/shell-ui.js`). Topbar has the pill search, notifications bell, role chip and avatar.
* **Role menus (v106 `00-role-menus`)**: added Sub-Admins, School Information (school profile), Result Display, Custom School Info, Email Settings, AI Comments (teacher), student Timetable, parent Contact School.
* **Students, Teachers, Classes, Subjects, Sub-Admins and Assign Subjects pages** restructured to the v106 layout: page header with a count and an Add button, the directory first, and the add / upload forms in collapsible panels (all fields, routes and buttons unchanged).
* **Score Entry** (teacher): page header with class / subject / term / max marks, Students / Scores saved / Not yet scored tiles, and Bulk Upload CSV moved into a collapsible panel. The React grid, per-row save, fallback form and CSV upload are untouched. Broadsheet and printed reports were left as they are so printouts do not change.
* **Sessions & Terms and Announcements** restructured the same way (header with counts and buttons, lists first, collapsible New Session / New Term / New announcement panels). Parents and Signup Codes already used the v106 page-head pattern. Status badges are now meaningful: Active / Disabled show green / amber, and plain badges are a neutral blue chip instead of the old gold/red.
* **Settings hub** now matches v106 #30: Change Password / My Profile tiles, username and contact forms side by side, School Settings as tiles (School Profile, Email Settings, Promote Students, Sub-Admins). The separate Sub-Admins card was folded into the tiles (same link). Clear Demo Data and Delete Account are unchanged. **Reports hub** shows its report cards in a responsive grid under the v106 page header (all forms and downloads unchanged).
* **Roll Call** (v106 #19): header with the school-time date, Class register / Attendance History buttons, live Present / Absent / Late / Excused / Total tiles that follow the radio buttons, centred radio columns. The form, correction-reason flow and save are unchanged. **Attendance History** has the v106 header. Staff Attendance and the Timetable hub already used the v106 header.
* **Portals**: student and parent dashboards, My Children, Link Child and Contact School already follow the v106 pattern, so they only needed the design layer. Added the v106 header to the shared **profile form** (student My Profile, staff and admin profile views; centred), the **admin view of a student's profile** and the **parent profile**, and rebuilt the **My Result** page header (eyebrow, term, action buttons - the printed result sheet itself is untouched). Student and parent portal pages render exactly the same set of routes as v111.
* New `tests/v112b_scenarios.py` (12 browser checks): drawer open/Esc, every collapsible Add panel opens from its button, roll-call tiles update, no JavaScript errors.
* **Dashboards (admin, teacher, parent, student)**: the live v111 dashboards already contain everything the v106 mock shows (welcome banner, quick access, KPI tiles, charts, tables), so they were not rewritten - they pick up the v106 look from the design layer. Fixed along the way: the parent/student/super-admin top-bar links were dark-on-blue and hard to read (white links, white pill for the current page), and the bar now reserves room for the floating font-size / theme controls so no link is hidden.
* **School Fees screen (#89) built**: `/admin/fees` (admin and sub-admin). Set the expected total, record and remove payments, see Expected / Collected / Outstanding / Rate and a recent-payments table. New table `school_fee_payments` (migration `fee_payments_v112`); the dashboard tile still reads `school_fee_summary`, which the screen keeps in step, and now links to the screen. Amounts are validated, students are checked against the school, and every action is audit-logged.
* Tests updated for intentional changes: `v75` (desktop now has the drawer + hamburger) and `v105` (the fees tile now links to the new screen). New `tests/v112_scenarios.py` (25 checks: fees screen, validation, tenant isolation, access control, menus, shell).

## Not changed on purpose
No routes, forms, field names, CSRF tokens, Jinja bindings, database code or permissions were changed. The v106 mock screens are static and simpler than the live pages (e.g. the real sign-in has class-code and school-ID fields), so they were used as a visual reference, not copied over.

## Still to do (next phases)
* Page-by-page structural redesign of the remaining screens (they already have the v106 look through the design layer).
* Phone-shell mock screens (m01-m05) - the existing mobile tab bar was kept and restyled.

## Screen map
| Mock screen | Title | v111 template(s) | Status |
|---|---|---|---|
| 00-role-menus.html | Menus by Role | `base.html nav` | n/a |
| 01-login.html | Login | `login.html` | Design layer (gradient hero, curved edge, rounded inputs); v111 unified login kept (class code, school ID, 3 signup paths) |
| 02-admin-dashboard.html | Admin Dashboard | `admin_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 03-result-sheet.html | Terminal Result | `result.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 04-parent-dashboard.html | Parent Dashboard | `parent_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 05-teacher-score-entry.html | Score Entry | `score_entry.html` | Page restructured (header, tiles, collapsible bulk upload); React grid untouched |
| 06-broadsheet.html | Broadsheet | `broadsheet.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 07-classes.html | Classes | `admin_classes.html` | Matched to mock layout (tiles / filters / flush table / link actions) |
| 08-students.html | Students | `admin_students.html` | Page restructured (header, KPI tiles, collapsible add/upload, directory table) |
| 09-teachers.html | Teachers | `admin_teachers.html` | Matched to mock layout (tiles / filters / flush table / link actions) |
| 10-subjects.html | Subjects | `admin_subjects.html` | Matched to mock layout (tiles / filters / flush table / link actions) |
| 11-parents.html | Parents | `admin_parents.html` | Matched to mock layout (tiles / filters / flush table / link actions) |
| 12-timetable.html | Class Timetable | `timetable_class_v2.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 13-grading.html | Grading Setup | `admin_grading.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 14-promote.html | Promote Students | `admin_promote.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 15-analytics.html | Analytics | `admin_analytics.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 16-teacher-dashboard.html | Teacher Dashboard | `teacher_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 17-student-dashboard.html | Student Portal | `student_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 18-result-workflow.html | Result Approval | `result_workflow.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 19-attendance.html | Student Attendance | `roll_call.html` | Page restructured (header, live tiles for roll call) |
| 20-materials.html | Learning Materials | `materials.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 21-notifications.html | Notifications | `notifications_inbox.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 22-billing.html | Billing Portal | `school_billing_portal.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 23-announcements.html | Announcements | `admin_announcements.html` | Matched to mock layout (tiles / filters / flush table / link actions) |
| 24-ai-assistant.html | AI Result Assistant | `ai_result_assistant.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 25-ai-comments.html | AI Comments | `ai_comments.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 26-ai-tutor.html | AI Tutor | `ai_tutor.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 27-theme-branding.html | Themes & Branding | `theme_branding.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 28-cumulative-result.html | Cumulative Result | `cumulative_result.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 29-staff-attendance.html | Staff Attendance | `staff_attendance.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 30-settings.html | Settings Hub | `settings_hub.html` | Page restructured (see notes) |
| 31-register.html | Staff Registration | `register.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 32-recover.html | Account Recovery | `recover.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 33-sessions-terms.html | Sessions & Terms | `admin_terms.html` | Page restructured (header with counts, lists first, collapsible add forms) |
| 34-assign-subjects.html | Assign Subjects | `admin_class_subjects.html` | Matched to mock layout (tiles / filters / flush table / link actions) |
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
| 45-student-result.html | My Result | `student_result.html` | Header / layout updated (see notes) |
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
| 59-student-profile.html | Student Profile | `student_profile.html` | Header / layout updated (see notes) |
| 60-ai-alerts.html | AI Alerts | `ai_alerts.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 61-result-settings.html | Result Settings | `result_display_settings.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 62-attendance-history.html | Attendance History | `roll_call_history.html` | Page restructured (header, live tiles for roll call) |
| 63-parent-profile.html | Parent Profile | `parent_profile.html` | Header / layout updated (see notes) |
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
| 77-subadmins.html | Sub-Admins | `admin_subadmins.html` | Mock file is empty in the supplied zip - shared v106 header and table used |
| 78-custom-fields.html | Custom Fields | `admin_custom_fields.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 79-result-permissions.html | Result Permissions | `result_permissions.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 80-audit-history.html | Audit History | `admin_audit_history.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 81-result-fields.html | Result Fields | `admin_result_fields.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 82-reports-hub.html | Reports Hub | `reports_hub.html` | Page restructured (see notes) |
| 83-parent-link-child.html | Link Child | `parent_link_child.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 84-admin-domains.html | Email Domains | `admin_domains.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 85-terminal-results-list.html | Terminal Results List | `class_results_list.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 86-registrar-dashboard.html | Registrar | `registrar_dashboard.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 87-parent-verification.html | Parent Verification | `admin_parent_links.html` | Design layer applied (modern tokens, cards, tables, forms, buttons, shell) |
| 89-school-fees.html | School Fees | `school fees (v105+)` | Built (new backend: payments table, route, template) |
| m01-admin-mobile.html | Admin Mobile | `phone shell` | n/a |
| m02-teacher-mobile.html | Teacher Mobile | `phone shell` | n/a |
| m03-parent-mobile.html | Parent Mobile | `phone shell` | n/a |
| m04-student-mobile.html | Student Mobile | `phone shell` | n/a |
| m05-analytics-mobile.html | Analytics Mobile | `phone shell` | n/a |
