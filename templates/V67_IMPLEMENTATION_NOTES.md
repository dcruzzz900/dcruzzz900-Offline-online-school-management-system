# V67 — Result Display Settings consolidation + Next Term Resumes (phase 2)

Second phase against the full "Functional and UI/UX Requirements" document,
covering P1 items 3–4: removing duplicate date fields scattered across the
app and replacing them with one single-source "Next Term Resumes" toggle
that automatically retrieves the *following* term's own resumption date.

## What changed

**Two old, overlapping fields are gone from result sheets and the result
editor:**

- The general **"Resumption Date"** toggle/field (`show_resumption_date`)
- The **"Result Date"** field on the result editor and result sheets
  (`show_result_date`, and the `result_date` input on `/result/<id>`)

**In their place, one new toggle: "Show Next Term Resumes."**

When it's on, a result sheet shows the resumption date that belongs to the
term *after* the one being viewed — never the term's own date, and never
guessed:

- First Term's sheet shows **Second Term's** resumption date.
- Second Term's sheet shows **Third Term's** resumption date.
- Third Term's sheet shows the **next session's first term's** resumption
  date.
- If that following term doesn't have a resumption date set yet, nothing is
  shown — it is never invented or copied from the current term.

Resumption dates themselves continue to be set the same way as before (per
term, from **Sessions & Terms** → `/admin/terms`, action "Set resumption
date"). Nothing about how a date is entered changed — only how it's chosen
for display, and where the "which terms get a resumption date" setting
lives (one toggle, one place, instead of three overlapping fields across
Theme & Branding / School Profile / Sessions & Terms / the result editor).

Toggling "Show Next Term Resumes" off and back on never deletes or alters
any stored date — it only hides/reveals it.

## Why nothing is lost

A migration (`next_term_resumes_v67`) runs once, automatically:

1. If a school previously had `show_resumption_date` on, the new
   `show_next_term_resumes` toggle is seeded to match (so nobody's display
   silently goes blank on upgrade).
2. The old `next_term_begins` field (entered on a term, meant to describe
   when the *following* term begins) is folded into that following term's
   own `resumption_date`, but only when that following term doesn't already
   have one of its own. No historical date is overwritten or discarded.

The `result_date` field is simply dropped from the result sheet/editor
display — per the requirements document, it was a duplicate of information
already shown elsewhere (term dates) and wasn't tied to anything else that
needs preserving.

## Where this was applied

- The shared result-sheet layout (`templates/_result_sheet.html`, used by
  the 9 CSS-grid template styles — Modern Academic, Formal School, Compact
  Academic, Detailed Report, Executive Band, Minimal Clean, Ledger Classic,
  Vibrant Cards, Split Header) and the CSS grid for each of those 9 styles.
- All 6 standalone "sample-inspired" sheet templates (Assessment Dossier,
  Boxed Grey Card, Clean Mid-Term Report, Green Cumulative Report, Progress
  Report Card, Peach Terminal Sheet).
- The default **Professional Classic** template, which doesn't use the
  shared CSS-grid partial at all — flows the "Next Term Resumes" line in
  automatically since it isn't grid-positioned.
- `/admin/result-display-settings` (Result Display Settings page) — the
  "Student details" section now has one "Term resumption dates" card
  instead of the old separate Resumption Date / Result Date cards, and its
  live preview reflects the new toggle.
- The result editor (`/result/<id>`) — the old "Result Date" input is gone.

## Database changes

One new migration step (`next_term_resumes_v67`) runs automatically the
first time the updated app starts: it adds the `show_next_term_resumes`
column, seeds it from the old toggle where applicable, and folds
`next_term_begins` values into the right term's `resumption_date` as
described above. As always, the app backs up `instance/school.db`
automatically before running any migration.

## Files changed

`db.py` (`RESULT_BOOL_SETTINGS`, new `term_sequence_next` /
`next_term_resumes_info` helpers, new `migration_067_v67_next_term_resumes`),
`app.py` (`build_result_data` now sets `rs["next_term_resumes"]` instead of
the old resumption/result-date logic), `v62_routes.py`
(`/admin/result-display-settings` route + live preview), `templates/_result_sheet.html`,
`static/css/result-sheet.css`, the 6 `templates/sheets/*.html` files,
`templates/result_display_settings.html`, `templates/result.html`.

## Tests

New `tests/v67_scenarios.py` (13 checks): nothing shown when unconfigured
on any of three terms; First Term's sheet shows Second Term's date and not
its own decoy date; Second Term's sheet shows Third Term's date; Third
Term's sheet shows nothing until the next session's first term gets a
date, then shows it; toggling off/on hides/restores display without
touching the stored date; the `next_term_begins`-folding migration step
works in isolation; another school's terms/dates are completely
unaffected. Full existing suite re-run: v60 (213), v61 (292), v62 (238),
v63 (107), v64 (116), v65 (235), v66 (17) — all still pass, no
regressions. 1,231 checks total across the whole suite, 0 failed.

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
   cp new_version/school-results/db.py school-results/db.py
   cp new_version/school-results/v62_routes.py school-results/v62_routes.py
   cp new_version/school-results/templates/_result_sheet.html school-results/templates/_result_sheet.html
   cp new_version/school-results/templates/result_display_settings.html school-results/templates/result_display_settings.html
   cp new_version/school-results/templates/result.html school-results/templates/result.html
   cp -r new_version/school-results/templates/sheets school-results/templates/
   cp new_version/school-results/static/css/result-sheet.css school-results/static/css/result-sheet.css
   ```
6. No new dependencies — reload isn't blocked on `pip install`, but it's
   safe to run anyway:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**. The new column/migration
   runs automatically on the first request.
8. Test it: go to **Sessions & Terms**, set a resumption date on your
   second term; open a student's First Term result — you should see
   "Next Term Resumes" with that date, not a blank or a date tied to First
   Term itself. Then check **Result Display Settings** → "Term resumption
   dates" card shows the one consolidated toggle, and the old "Result
   Date" field is gone from the result editor.

## Still outstanding (next phases)

Annual/cumulative calculation review, Domain Ratings rename + combined
grading key display, drafts/approval/publish permission separation,
template fixes (Executive Band, Compact Academic, Clean Mid-Term — incl.
removing its "Highest" column, Continuous Assessment Dossier passport
positioning), orientation + Fit to Page + font scaling for print/PDF,
mobile responsiveness pass, and hiding instructional text by default. Tell
me which to do next.
