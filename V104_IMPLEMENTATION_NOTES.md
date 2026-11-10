# V104 - ten additional requirements

1. **Announcements**: Super Admin (all schools or one) and School Admin (own school only) publish banners with audience, style, start and a required expiry (entered in school local time, stored UTC). Shown on dashboards, dismissible per user, hidden at expiry, purged 24h later. Tables announcements / announcement_dismissals. Pages: /admin/announcements, /platform/announcements.
2. **Form teacher attendance**: Staff Attendance removed from teacher menu, dashboard and reports hub; "Student Attendance" (/my-class/attendance) goes to the teacher's own class(es) only; roll call re-checks assignment.
3. **Result sheet / terms**: terms never activated by the admin are not shown (terms.activated_at, back-filled); cumulative scores 7.3pt (was 6.4) with re-balanced columns, measured no overflow; PDF signatures centred (and the print line-wrapper fixed); a class result's sheet design + settings are frozen at publish (result_publication.sheet_snapshot; results published before this version are frozen once at start-up).
4. **Passports**: one frame size/fit everywhere (img.passport-img: cover, no stretching); duplicate upload card removed from the student profile page - Edit Profile has the single upload.
5. **Admission/Staff ID**: Admission No. unique per CLASS (school-wide index + triggers replaced; same number allowed in different classes; login keeps refusing ambiguous matches). Staff / Employee ID required at admin registration and staff self-signup, unique per school, no longer admin-only.
6. **Navigation**: menu grouped (Academics, Attendance, Teaching, People, Reports & Insights, Communication, School Administration) and filtered by role; no duplicate links; hamburger rewritten (aria, Escape, backdrop, close on link/resize/back-cache, in-menu Close button, menu stacked above backdrop).
7. **CSV imports** (students, class register, scores): shared csv_import.py; headings = database fields; row/column error messages; ALL-OR-NOTHING (nothing saved unless every row is valid); blank cells never erase saved data; score template has only admission_no, ca1, ca2, [ca3], exam.
8. **Custom School Information**: now in the menu; each field can be shown on result sheets; display switch "Show custom school information"; prints in the header (HTML + PDF).
9. **Custom result fields**: Additional Result Fields (text / number with max / choice) with name, order, visibility; filled per student under Update Result Details; "Additional Information" block on sheet + PDF (all 6 designs); domains and their items can now be re-ordered (up/down); custom domains were already supported.
10. **Tests**: tests/v104_scenarios.py (75 checks). All suites v60-v103 pass, plus the 73 pytest-style tests (run with a small shim, pytest is not installed in this environment).

## Known limits
* PostgreSQL: new tables/columns use portable SQL, but triggers/AUTOINCREMENT follow the rest of the code base (SQLite). MIGRATION_POSTGRES.md still applies (not testable here).
* Additional fields / school information appear on result sheets and PDFs; broadsheets and other reports do not list them.
* Published-sheet lock freezes design + settings; renaming an additional field or school-info label later still changes labels on published sheets.
* Student and parent banners use the same code as staff banners but are covered only by staff-role tests.
* Offline/online sync code was not touched.
