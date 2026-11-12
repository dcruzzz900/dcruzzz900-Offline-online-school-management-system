# V70 — Domain Ratings rename + combined grading key display (phase 5)

Fifth phase against the full "Functional and UI/UX Requirements" document,
covering the P1 item: rename "Educational Domains" to "Domain Ratings"
everywhere, and combine the grading key and the domain-rating key into one
display instead of two separate, scattered key blocks.

## What changed

**"Educational Domains" is renamed to "Domain Ratings" everywhere it's
user-facing:**

- The **Domain Ratings** admin settings page (was "Educational Domains")
- The result editor's rating section heading
- The "Domain Ratings" heading on every result sheet template that shows
  one (the 9 CSS-grid styles and Clean Mid-Term Report)
- The dashboard-search feature label
- The PDF broadsheet/cumulative export heading

The underlying database table is still named `educational_domains` — that's
an internal schema name, not something anyone sees, so it wasn't touched
(renaming it would mean a migration with real risk for zero visible
benefit).

**The grading key and the domain-ratings key are now shown together, as
one combined key, wherever both would otherwise appear separately:**

Before, a result sheet could show the grade scale (A/B/C… score ranges) in
one place and the domain-rating legend (1 = Poor … 5 = Excellent) in a
completely different spot — sometimes right next to the "Domain Ratings"
heading, sometimes as its own stray line, never together. Now every
template shows ONE combined key section/box with both parts, each still
independently controlled by its own existing toggle:

- Grading key only (domains off): shows just the grade scale, as before.
- Domain ratings only (grading key off): shows just the rating legend —
  this still works; turning one off never hides the other.
- Both on: both appear together in the same key block, clearly labelled
  "Grades:" and "Domain ratings:".
- Both off: no key section renders at all.

This was applied to the shared CSS-grid template family (`_result_sheet.html`,
used by Modern Academic, Formal School, Compact Academic, Detailed Report,
Executive Band, Minimal Clean, Ledger Classic, Vibrant Cards, Split
Header) and to all 6 standalone sample-sheet templates (Assessment
Dossier, Boxed Grey Card, Clean Mid-Term Report, Green Cumulative Report,
Progress Report Card, Peach Terminal Sheet — the last already showed each
rating's meaning inline, so it needed no separate key and was left as-is).

**A real gap this closed:** Progress Report Card previously showed domain
ratings as a bare "4/5" with no legend anywhere on the sheet — there was
no way for a parent to know what "4" meant. It now gets the same combined
key box as every other template.

## Files changed

`templates/_result_sheet.html`, `templates/sheets/clean_midterm_report.html`,
`templates/sheets/green_cumulative_report.html`,
`templates/sheets/assessment_dossier.html`,
`templates/sheets/boxed_grey_card.html`,
`templates/sheets/progress_report_card.html`, `templates/result.html`,
`templates/admin_domains.html`, `static/css/result-sheet.css`,
`v61_routes.py` (nav/search label), `v64_spec.py` (quick-action label),
`pdf_utils.py` (broadsheet/cumulative PDF heading), `db.py` (the
"Show Domain Ratings" toggle's display label).

## Database changes

None. No migration — this is display/wording only; the `educational_domains`
table and its data are untouched.

## Tests

New `tests/v70_scenarios.py` / `tests/test_v70_behavior.py` — 39 checks
across every one of the 13 result templates: the old "Educational Domains"
name never appears anywhere (nav search, admin page, result editor, or
any of the 13 templates); when both keys are on they appear together;
each key still works independently when the other is off; neither
renders when both are off; Progress Report Card's previously-missing
domain legend is now actually present; the PDF export carries the same
combined key as the on-screen/print view. Also fixed two existing tests
whose literal-text assertions were tied to the old wording
(`tests/v64_scenarios.py`'s nav-label check, `tests/v61_scenarios.py`'s
result-editor heading check, and `tests/v65_scenarios.py`'s keyword list
for detecting a key block) — an intentional wording change, not a
regression.

Full existing suite re-run: v60 (213), v61 (292), v62 (238), v63 (107),
v64 (116), v65 (235), v66 (17), v67 (13), v68 (12), v69 (20) — all still
pass, no regressions. 1,302 checks total across the whole suite, 0
failed.

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
   cp new_version/school-results/db.py school-results/db.py
   cp new_version/school-results/v61_routes.py school-results/v61_routes.py
   cp new_version/school-results/v64_spec.py school-results/v64_spec.py
   cp new_version/school-results/pdf_utils.py school-results/pdf_utils.py
   cp new_version/school-results/templates/_result_sheet.html school-results/templates/_result_sheet.html
   cp new_version/school-results/templates/result.html school-results/templates/result.html
   cp new_version/school-results/templates/admin_domains.html school-results/templates/admin_domains.html
   cp -r new_version/school-results/templates/sheets school-results/templates/
   cp new_version/school-results/static/css/result-sheet.css school-results/static/css/result-sheet.css
   ```
6. No new dependencies and no database migration this time:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**.
8. Test it: open **Domain Ratings** under School Setup (was "Educational
   Domains") and a student's result with both the grading key and domain
   ratings switched on — you should see one combined key box with both
   "Grades:" and "Domain ratings:" lines, in both the web view and the
   PDF.

## Still outstanding (next phases)

Draft/approval/publish permission separation (gap-closing pass), template
fixes (Executive Band, Compact Academic, Clean Mid-Term — incl. removing
its "Highest" column, Continuous Assessment Dossier passport
positioning), print/PDF orientation + Fit to Page + font scaling, mobile
responsiveness pass, and hiding instructional text by default. Tell me
which to do next.
