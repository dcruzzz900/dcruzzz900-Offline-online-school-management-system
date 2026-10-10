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
