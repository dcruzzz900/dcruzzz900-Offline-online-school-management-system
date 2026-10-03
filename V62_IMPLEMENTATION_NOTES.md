# V62 — consolidated bug fixes and enhancements

Test status: `python tests/v62_scenarios.py` → 380 checks, 0 failed. `python tests/v60_scenarios.py` → 213 checks, 0 failed.
The 47 pytest-style files in `tests/test_*.py` also pass (run with pytest, or any runner that calls each `test_*` function).
`tests/v61_scenarios.py` was replaced by `tests/v62_scenarios.py` because the settings page moved.

## Fixed (verified by tests)
| # | Item | What was wrong / what changed |
|---|------|-------------------------------|
| 1 | Roles & Scope 500 | Template used `ROLE_CATALOG`, which the route never passed. Passed now; checkboxes show saved permissions. |
| 1 | "Session timed out" on Make Ready for Live Data / Continue to School Setup | Both forms lacked the CSRF token. Added to those and 16 other POST forms. CSRF failures are now logged. |
| 5, 29 | Role changes active immediately | One function (`change_staff_role`) updates the role, retires the old assignment, writes the audit log. Session role is refreshed from the database on every request. Staff signup gives the default Teacher role. |
| 6 | Subject Teacher | Can enter scores only for assigned subjects; no results/broadsheet access. Score entry and CSV upload require a current teaching role. |
| 7 | Class/Form Teacher | Own class results and broadsheet only. |
| 2, 14 | Result Display Settings | One page (`/admin/result-display`) with every switch, five templates and the look/wording options. Duplicates removed from Theme & Branding and School Profile. |
| 3, 18 | Passport and logo | OFF = hidden; ON without photo = blank area (no avatar). Logo keeps its aspect ratio and follows its toggle. |
| 8, 9 | Comments / Principal sign date | Separate fields, inputs, permissions and display. Principal sign date saved and shown. |
| 10, 11 | Result date / "Issued" | Date stored per student per term; "Issued" line removed. |
| 12, 13 | Attendance | Comes from the daily register when present, else manual. Validation: Present + Absent = Opened; no negatives; neither exceeds Opened. |
| 15 | Templates | Classic, Modern, Formal, Compact, Detailed — same data and settings. |
| 16 | One-page printing | Print page and PDF fit one A4 page. Checked in real Chromium PDFs for all five templates with 26 subjects: 1 page, signatures and grading key visible. |
| 17 | Broadsheet printing | Dedicated landscape print pages (term and cumulative), no app chrome. |
| 4 | Passport visibility | Staff passport: School Admin/Sub-Admin and the person only. Parent passport (new upload page): School Admin/Sub-Admin and the parent. Student passport: School Admin and the class's Form Teacher. All scoped to the school. |
| 19 | Custom school fields | `/admin/school-info`: add / rename / edit / remove, case-insensitive unique names, audited. |
| 20 | School ID | `SCH-<ABBR>-0001` style, per-abbreviation sequence, database trigger prevents any later change. Existing schools keep their current IDs. |
| 22 | Greeting | Morning / afternoon / evening from the viewer's own clock. |
| 23 | AI cards | Wrapping, larger text, higher contrast, no clipping. |
| 24, 25 | Super Admin menu | Toggle works at every size (remembered on wide screens); text un-clipped and high contrast. |
| 21 | Login/signup | No horizontal overflow at 320, 360, 768, 1366, 1920 px (measured in Chromium). Hero heading contrast fixed; short screens compacted. |
| 26 | Usernames | Case preserved; lookups and uniqueness are case-insensitive. |
| — | Existing bug found | Parent login crashed (database connection closed then reused). Fixed. |

## Behaviour changes to be aware of
* A School Admin role change replaces the old role (roles no longer stack).
* School Admin and Sub-Admin keep access to staff passports; other staff no longer see them.
* Result settings moved to `/admin/result-display`; the old URL redirects.
* Run on startup: migration `v62_result_display` (new columns, `school_info_fields` table, School ID trigger).

## Not verified
* The acceptance matrix was not run in full across all nine roles on real phones/tablets. Role coverage in tests: School Admin, Class/Form Teacher, Subject Teacher, other-school Admin, parent, anonymous. Not covered: Super Admin result views, Sub-Admin, Principal and Student against every new route.
* Login pages were measured at five widths and spot-viewed; signup pages other than New School were not screenshot-reviewed. `/staff/signup` returned 404 at the path I guessed, so staff signup layout was not reviewed.
* Super Admin menu and AI card were verified by CSS/markup checks, not by clicking in a browser.
* Browser print of the result was tested by generating PDFs in headless Chromium, not by pressing Print in Safari/Firefox.
