# V77 — Broadsheet mobile header fix + sign-date auto-populate

This covers the two things you asked for on 2026-10-18:

> "On Broadsheet 1st CA appear on S/N column. Adjust it. When a principal or teacher set date on
> result sheet populate it to the whole of the result sheet for that particular term."

## 1. Broadsheet "1st CA appears under S/N" — fixed

**What was actually wrong.** It wasn't the mobile view specifically — on closer investigation
(rendering the real page in a browser, not just reading the HTML) this happened on desktop too,
you just hadn't scrolled sideways far enough to notice it. The broadsheet's header has two rows:
row 1 has "S/N"/"Student" spanning both rows, and each subject's name across 4 columns; row 2 has
"1st CA/2nd CA/Exam/Total" under each subject. A site-wide script (added for a different feature —
automatically giving every table on the site a heading) pulls a table's first row out into its own
`<thead>` whenever a table doesn't already define one. For a normal single-row-header table that's
harmless. For the broadsheet's two-row header, it tore row 1 and row 2 apart: once row 1 was moved
into its own section, the browser no longer treated row 2 as "the second row of the same header" —
it started a brand-new row count from column 1, which is exactly why "1st CA" landed under "S/N"
and "2nd CA" landed under "Student".

**The fix.** `templates/broadsheet.html` now wraps both header rows in an explicit `<thead>` and
the student rows in a `<tbody>`, the same way several other tables in the system already do. Since
the table now has its own `<thead>`, that site-wide script leaves it alone, and the two header rows
stay together the way the HTML always intended.

While investigating this I also found a second, narrower issue that would have shown up once the
first was fixed: on small phone screens, a separate site-wide rule turns every table into
`display:block` so it can scroll sideways. That rule also breaks two-row headers (for the same
underlying reason — `display:block` throws away the table's row/column grid that rowspan/colspan
need). The broadsheet already has its own horizontal-scroll wrapper, so it doesn't need that
site-wide rule. `static/css/responsive-ui.css` now exempts the broadsheet's table (via a new
`.bs-table` class, also added in the template) from that rule on phone-width screens.

Both fixes were checked by actually rendering the page in a headless browser at both a normal
desktop width and a 375px phone width and reading back where each header cell actually landed on
screen — not just by reading the HTML, since the HTML looks identical whether this bug is present
or not.

**Files changed:** `templates/broadsheet.html`, `static/css/responsive-ui.css`.

## 2. Sign date now auto-populates the rest of the term's result sheets

Previously, the teacher's and principal's sign-off date on the "Update Result Details" page only
applied to the one student you were editing — you'd have had to open every single student's result
and re-enter the same date by hand.

Now, per what we agreed on:
- **Teacher's sign date**: setting it on any one student's result also sets it on every other
  student in **that teacher's own class**, for that term.
- **Principal's sign date**: setting it on any one student's result also sets it on **every
  student in the whole school**, for that term.

A few things this deliberately does NOT do, to keep it safe:
- It only ever touches the sign date (and who signed it) on the other students. Nothing else on
  their result — comments, attendance, anything else — is touched.
- If a class's result for that term has already been submitted, is under review, approved, or
  published, that class is **skipped** by the propagation — exactly the same protection that
  already stops you from editing a locked class's comments directly. So a principal setting a
  school-wide date can never accidentally slip a change into a class that's already been locked
  down.
- Saving the same date again (no change) does not re-run the propagation, so it won't spam the
  audit log every time someone re-opens and re-saves the same result.
- Every bulk update is recorded in the audit log, same as any other change in the system.

**Files changed:** `app.py` only. No database migration needed — this uses the existing
`student_term_info` table and existing columns; nothing new was added to the schema.

## Testing

- `tests/v77_scenarios.py` (+ `tests/test_v77_behavior.py` pytest wrapper) — new, covers both
  fixes end-to-end: real HTTP requests for the sign-date propagation (including the "don't touch
  a locked class" and "don't touch other fields" checks), and a real headless-browser render for
  the header alignment check.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v77_scenarios.py`): **1,449
  checks, 0 failed.** No existing test needed to change.

## Installing this update on PythonAnywhere

This is a normal update — no new database columns or tables, so there's nothing special to run
after uploading; just reload the app.

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v77.db
   ```
3. Upload the new zip and replace these files (or just unzip over the existing `school/` folder,
   keeping your existing `instance/` folder, which holds your live database, untouched):
   - `templates/broadsheet.html`
   - `static/css/responsive-ui.css`
   - `app.py`
   - `tests/v77_scenarios.py` (new)
   - `tests/test_v77_behavior.py` (new)
4. Go to the **Web** tab and click **Reload** on your web app.
5. Open the Broadsheet page for any class on your phone (or narrow your browser window) to confirm
   "1st CA" now sits under the right subject. Then open any student's result, set a sign date, save
   it, and check that the same date now shows up on the other students in that class/school for
   that term.

That's it — no migration step, no new settings to configure.
