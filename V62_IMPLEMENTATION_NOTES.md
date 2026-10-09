# V62 — notes

## Install (same as before)
1. Back up your database. 2. Unzip over the project folder (leave `instance/` alone). 3. Reload the web app — the database upgrades itself.
`select * from migration_notes;` lists any unique index skipped because old data already had duplicates.

## Root causes found
* **Roles & Scope 500** — the template used `ROLE_CATALOG`, which was never registered as a template global (it only broke once an assignment existed).
* **"Session timed out" on Make Ready for Live Data and Continue to School Setup** — those forms (18 in total, including several Super Admin forms) were posted
  without the hidden security token, so the CSRF check rejected them. All 18 now send it, a test fails if any POST form ever lacks one, and every refusal is logged
  with the real reason (no session / form sent no token / token mismatch).
* **Parent login crashed** — the code queried a database connection it had just closed. Fixed.
* **Role changes were only visual** — they now close the old assignment, create an ACTIVE one with its permissions, update the open session on the very next request,
  and write to both the role audit table and the protected audit history. No Super Admin approval step.
* **Result date vanished** — it was never stored (the sheet used today's date). It is now saved per result, with an optional per-term default.

## New / changed
* School Setup → **Result Display Settings** (`/admin/result-display-settings`): the only place for result visibility/presentation; old controls removed from School Setup.
* 5 result styles, one-page print and PDF, dedicated print pages for results and broadsheets, shrink-to-fit rather than cut-off.
* Teacher and Principal comments: separate columns, inputs, permissions and boxes. Principal sign date added.
* Attendance flows from the daily register; manual entry is validated (Present + Absent = Opened).
* Professional School ID (`SCH-GONI-0001`), permanent, not editable. The old code keeps working as a login alias.
* Custom school information, parent passports (School Admin can view), time-based greeting, readable AI card, collapsible Super Admin menu, responsive login CSS.
* Staff usernames keep their case; uniqueness and login are case-insensitive.

## Tests
`tests/v62_scenarios.py` (248), `tests/v61_scenarios.py` (292), `tests/v60_scenarios.py` (213), plus the original suite (47).


## V62.1 – consolidated operations spec (Doc 4)

Implemented and covered by `tests/v62_workflow_scenarios.py` (94 checks) plus the earlier suites (V60 213, V61 293, V62 248, legacy 48):

* **Multiple simultaneous staff roles** (`/admin/teachers/<id>/roles`): all active immediately, permissions are the union, School Admin cannot be assigned as a staff role, all changes audited (append-only).
* **Score permission by real assignment** (`can_enter_scores`): a user with any role (e.g. Discipline Master) who is assigned subject + class/arm may enter scores; nothing else. Score audit stores actor, roles, action (entered/edited/cleared/corrected), arm, server timestamp.
* **Registrar / Admissions** (`/registrar`, `/admin/student-statuses`): admission/register numbers (unique, case-insensitive, per school), transfer/withdraw/suspend/graduate/expel/activate with reasons, immutable status history, school-defined statuses.
* **Strict attendance**: server clock in the school's timezone; future/backdated dates refused; one record per day; corrections only via the correction workflow (reason, old/new kept, append-only log); same rules for staff check-in/out.
* **Notifications**: per-reader read state, red unread count, green unread rows, instant mark-read (staff, students, parents).
* **Result workflow** DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED → PUBLISHED, RETURNED, REOPENED (reasons required for return/reopen). Print, PDF, broadsheet PDF, export and e-mail are blocked **on the server** for anything unpublished, for every role; publishing needs the explicit publish permission. Pre-existing published terms are migrated as PUBLISHED.
* **One sheet model** (`sheet_model.build_sheet`) feeds the on-screen preview, the report and the PDF; five result styles; separate subject/class/principal comments.
* Student login works without a class code (class codes remain optional).

Verification notes: all suites run against a fresh database through the real Flask request cycle with CSRF tokens; a V61 database was upgraded in place (schema 68 → 70) with a published term preserved; 820 GET pages crawled as school admin / platform admin / teacher / student with no 5xx. Visual layout (CSS, mobile header, PDF look) was checked by markup/PDF generation only, not in a real browser.

Test helpers: older suites use `set_state()` / `set_all()` to put a class straight into a workflow state, because printing and score edits now depend on it.
