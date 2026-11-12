# V69 — admin-wide (bulk) AI consent management (closing the last P0 item)

Fourth phase against the full "Functional and UI/UX Requirements" document.
This closes the one P0 item left over from the original audit: AI consent
could only ever be set one student at a time, with no way to apply a
status to many students in one action.

## What changed

**Result Display Settings → AI Consent** now has a "Bulk consent update"
panel above the existing per-student table (which still works exactly as
before — nothing about single-student editing changed).

The bulk panel lets an admin:

1. Optionally filter the student list down to one class.
2. Select any number of students (multi-select, with "Select all shown"
   and "Clear selection" buttons).
3. Choose a new status — Pending, Granted, or Withdrawn — and apply it to
   everyone selected in one submit.

Typical uses this was built for: a school-wide policy change ("withdraw AI
processing consent for everyone while we review our privacy notice"), or
logging a batch of paper consent forms collected at the start of term in
one go instead of 40 separate clicks.

**Setting "Granted" in bulk still requires saying who gave it and in what
capacity** — exactly like the single-student form already required. You
can't grant consent on someone else's behalf anonymously just because
it's a bulk action; for a batch of collected paper forms, "School
representative" (already an existing relationship option) is there for
exactly this case.

## Why this is as safe as the one-at-a-time version

Bulk update does not introduce a second, weaker way to record consent —
it calls the exact same single-writer function (`record_ai_consent`) once
per selected student, so:

- Every student still gets their own row in the consent-history table,
  with their own timestamp and their own "previous status → new status"
  entry — nothing is merged or summarized away.
- A student already at the target status is left alone and not re-logged
  (so re-running a bulk action is harmless and the history doesn't fill up
  with no-op entries).
- A student id posted that doesn't belong to the admin's own school is
  silently ignored — tenant isolation is enforced the same way as every
  other query in the app (scoped by the session's school_id, never by a
  client-supplied id).
- One summary line is also written to the general audit log
  (`ai_consent_bulk_changed`, with the count and new status) in addition
  to each student's own history event, so "who ran a bulk change and
  when" is itself auditable.

## Database changes

None. No migration — this reuses the existing `student_ai_consent` /
`student_ai_consent_events` tables and the existing single-writer function
exactly as they were.

## Files changed

`app.py` (new `_ai_consent_bulk()` helper; `ai_consent()` route now
dispatches to it when the bulk form is submitted; class list added to the
page's context), `templates/ai_consent.html` (new bulk-update panel with
class filter, multi-select, select-all/clear, and client-side guard
against submitting with nothing selected).

## Tests

New `tests/v69_scenarios.py` / `tests/test_v69_behavior.py` — 20 checks:
bulk withdraw applies to exactly the selected students and no others;
each selected student gets their own history event, not a shared one;
re-applying the same bulk status is a no-op (0 changed, no duplicate
history); bulk "Granted" without a name+relationship is refused; bulk
"Granted" with one succeeds for every selected student, each recording
the same consenting name on their own row; an invalid status is rejected;
submitting with no students selected is refused with a clear message, not
a silent no-op; another school's student id in the same submission is
silently excluded while the caller's own students in that submission
still go through; a summary audit-log entry is written for the bulk
action. Also added the missing pytest wrapper for v68
(`tests/test_v68_behavior.py` already existed; confirmed present).

Full existing suite re-run: v60 (213), v61 (292), v62 (238), v63 (107),
v64 (116), v65 (235), v66 (17), v67 (13), v68 (12) — all still pass, no
regressions. 1,263 checks total across the whole suite, 0 failed.

## Steps (PythonAnywhere)

1. Log in to **pythonanywhere.com** → **Files** tab, upload the new
   `school-result-system.zip` to your home directory.
2. **Consoles** tab → open a **Bash** console.
3. Back up your database first (also happens automatically, but do it
   yourself too):
   ```
   cd school-results
   python backup_db.py
   ```
4. Unzip the new version to a temporary folder:
   ```
   cd ~
   unzip -o school-result-system.zip -d new_version
   ```
5. Copy over the changed files only:
   ```
   cp new_version/school-results/app.py school-results/app.py
   cp new_version/school-results/templates/ai_consent.html school-results/templates/ai_consent.html
   ```
6. No new dependencies and no database migration this time:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**.
8. Test it: go to **AI Consent**, use the new "Bulk consent update" panel
   to select a few students (try the class filter and "Select all shown"),
   set a status, and confirm the table above updates and the history
   below shows one entry per student.

## Still outstanding (next phases)

This closes the last P0 item. Remaining from the requirements document:
Domain Ratings rename + combined grading key display, draft/approval/
publish permission separation (gap-closing pass), template fixes
(Executive Band, Compact Academic, Clean Mid-Term — incl. removing its
"Highest" column, Continuous Assessment Dossier passport positioning),
print/PDF orientation + Fit to Page + font scaling, mobile responsiveness
pass, and hiding instructional text by default. Tell me which to do next.
