# V64 — master-spec items not already in V63

| Spec | What was done |
|---|---|
| 38 Timetable error | Root cause: the validator's conflict logger bound a Python dict to the `entity_type` column, so generating a draft crashed (internal server error) whenever a requirement was not fully scheduled. Fixed. Generation now only schedules real subject assignments (a subject with no teacher is reported with "Assign a teacher…", never invented); teacher/class double-booking is still prevented. |
| 37 Setup 100% | When every setup check passes the school is activated automatically (LIVE / ACTIVE): audit entry `school_auto_activated`, a notification to the School Admin, once only. Runs on the setup wizard, the dashboard and after admin changes. A suspended/incomplete school never passes the gate. |
| 6 Staff titles | Optional title (Mr., Mrs., Master, Miss, Dr., Prof. or school-defined) on Manage roles; shown as "Dr. John James" in the staff list and student subject list; audited. |
| 8 Assign Subjects | Link added to the Academic workspace; assignment changes already drive score-entry permission. |
| 9, 39, 40 Quick Actions | One partial on the staff, admin, student and parent dashboards. Staff actions are combined from every role (Subject/Form Teacher, Registrar, review/publish permission holders, admin). Indicators: "3 Classes Pending", "Today — Not Taken", "2 Awaiting Review", "5 Unread", with Available / Pending / Completed / Requires Attention / Locked / Not Yet Published. "View All Actions" after 8. Shortcuts only — target pages still enforce RBAC. |
| 40 Parent | All linked children are listed; one is selected (`?child=`), only linked children can be selected, and the dashboard and actions follow the selection. New "Contact School" page. |
| 39 Student | New My Attendance, My Timetable (published only), My Subjects pages. |
| 35 Status indicators | 🟢 Active · 🟠 Suspended · 🔴 Withdrawn · 🔵 Transferred · 🟣 Graduated · ⛔ Expelled — always with the text — in the student list, registrar, history and class register. |
| 29 Broadsheet | Per subject: 1st CA, 2nd CA, (3rd CA), Exam, Total in the screen, print and PDF views. CA3 appears only when the school's CA3 maximum is above 0. |
| 27 Result styles | Five new, structurally different styles (Executive Band, Minimal Clean, Ledger Grid, Vibrant Cards, Split Header) → 10 in total, each with its own header, information block, table and headings in both the HTML/print CSS and the PDF builder. |
| 17 Comments | The class-teacher and principal auto-comments used the same bank (identical wording). They now use separate banks. |
| 3 Settings | Authentication branding removed from School Profile; Theme & Branding is the only place. |
| 2 Super Admin dashboard | Added Trial schools, Parents, Results generated, Results published, Pending tasks, Notifications. |
| 14–15 | One clock only (header), anchored to server time in the school timezone: "Thursday, 08/10/2026 — 1:07 AM". The unused/duplicate clock partial and the extra clock line on the teacher dashboard were removed. |
| 16 | Verified: saving identical scores writes no audit rows, so history lists only students whose scores changed. |

## Honest limits
* The PDF is built by a separate reportlab layout that mirrors the HTML/print sheet (same settings and structure per style); it is close but not pixel-identical (e.g. the Vibrant Cards gradient header is a solid band with a coloured rule in the PDF; the Ledger paper tint is not applied).
* Not re-done because they were already in earlier versions and their tests still pass: Super Admin hamburger menu, logo/passport/signature handling, display toggles, custom fields, tenant checks.
* Student-facing "Messages" and "Assignments" have no feature behind them in this codebase, so there is no Quick Action for them (the spec says "where implemented").

Tests: `python tests/v64_scenarios.py` (94), v63 (107), v62 (248), v61 (292), v60 (213), 45 contract tests.

## Update — Preview = Print = PDF (screenshots: downloaded PDF looked different from the print view)
Cause: the PDF was drawn by a separate reportlab layout, so it could never match the HTML print page.
Fix: `html_pdf.py` now produces every result PDF (single, class bulk, parent, student, e-mail attachment) by printing the
**same print page** (`result_print.html` + `result-sheet.css`) with headless Chromium in print mode. Subresources (CSS, logo,
passport, signatures) are fetched through the app with the caller's own session, so tenant/permission checks still apply; other
hosts are blocked. Bulk PDFs print one sheet per student and merge them.
* Deploy: `requirements.txt` now lists `playwright` and `pypdf`; `nixpacks.toml` installs Chromium on Railway
  (`playwright install chromium`). PythonAnywhere cannot run Chromium — there the code falls back to the older reportlab
  builder (not identical); on such hosts use Print → "Save as PDF" from the print page, which is identical.
* Fixed: the "Overall position" card was unreadable (white on light) in Executive Band, Vibrant Cards and Split Header.
Tests: v64 now 105 checks (adds PDF parity: one A4 page, same content as the print page, class PDF = one page per student, fallback when no Chromium).

* Railway build fix: the first `nixpacks.toml` hard-coded apt names (`libasound2` has no candidate on Ubuntu 24.04). It now uses `playwright install --with-deps chromium`, which selects the right packages for the image; if that step fails the build still completes and PDFs fall back to the older builder.
