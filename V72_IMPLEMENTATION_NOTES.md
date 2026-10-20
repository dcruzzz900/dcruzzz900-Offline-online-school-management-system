# V72 — Result-sheet template fixes: Clean Mid-Term "Highest" column, CA Dossier passport overlap

Seventh phase against the full "Functional and UI/UX Requirements" document, covering two
of the four items in its template-fix list: Clean Mid-Term Report's "Highest" column
removal, and Continuous Assessment Dossier's passport positioning.

The other two items in that list — Executive Band and Compact Academic — were audited
first. Both templates were checked structurally (every grid-area the CSS expects has a
matching HTML section, and vice versa; the colour-band header already carries the
print-color-adjust rule it needs) and nothing jumped out as broken. Since the original
note didn't say what's specifically wrong with either of those two (unlike the other
two items, which named an exact column and an exact field), I didn't want to guess at a
cosmetic preference and fix the wrong thing. **I need a description or screenshot of what
looks wrong on Executive Band and Compact Academic before touching them** — tell me what
you're seeing (or not seeing) on those two and I'll fix it next.

## What changed

**Clean Mid-Term Report:** removed its "Highest" (the class's highest score in that
subject) column entirely — header and data cell both. This was the only one of the
sample-sheet templates asked to drop it; Boxed Grey Card, Progress Report Card and Peach
Terminal Sheet each still show their own Highest/Lowest columns exactly as before — this
phase doesn't touch those.

**Continuous Assessment Dossier:** fixed the passport photo overlapping the assessment
table below it. The photo sits absolutely-positioned over a short, two-line identity
block (name/class/year, then admission no./average/position) so those two lines can wrap
narrower to make room for it. The bug: an absolutely-positioned element never adds to its
parent's height, so the identity section's box was only as tall as its own two lines of
text (about 12mm) while the photo itself is 30mm tall — the bottom third of the passport
photo hung down past the identity section and collided with the table directly under it.
Fixed by reserving the photo's full height on the identity section (so the box is always
tall enough to contain it) and removing an odd `-1mm` top offset that nudged the photo up
and made the overhang slightly worse.

## Why this holds

- The "Highest" column is purely presentational (one `<th>`/`<td>` pair) — removing it
  doesn't touch how `s.highest` is computed anywhere else, so every other template that
  still shows it (and the underlying data) is completely unaffected.
- The passport fix is CSS-only (a `min-height` on the container, and the photo's own top
  offset) — no HTML structure, no other template's CSS, and no scoring/data logic changed.

## Files changed

`templates/sheets/clean_midterm_report.html`, `static/css/result-samples.css`.

## Database changes

None.

## Tests

New `tests/v72_scenarios.py` / `tests/test_v72_behavior.py` — 9 checks: Clean Mid-Term
Report's print view no longer contains a "Highest" column or label anywhere, while
"Average" and the normal score/grade cells still render correctly; Boxed Grey Card and
Progress Report Card still show their own Highest/Lowest columns unchanged (proving the
fix was correctly scoped to one template); the CSS now reserves the passport's full
height on Continuous Assessment Dossier's identity section and no longer offsets the
photo above its container; that template still renders its passport, identity section
and assessment table correctly.

Full existing suite re-run: v60 (213), v61 (292), v62 (238), v63 (107), v64 (116), v65
(235), v66 (17), v67 (13), v68 (12), v69 (20), v70 (39), v71 (30) — all still pass, no
regressions. 1,341 checks total across the whole suite, 0 failed.

## Steps (PythonAnywhere)

1. Log in to **pythonanywhere.com** → **Files** tab, upload the new
   `school-result-system.zip` to your home directory.
2. **Consoles** tab → open a **Bash** console.
3. Back up your database first (also happens automatically, but do it yourself too):
   ```
   cd school-results
   python backup_db.py
   ```
4. Unzip the new version to a temporary folder (this zip's files are all under a top-level
   `school/` folder):
   ```
   cd ~
   unzip -o school-result-system.zip -d new_version
   ```
5. Copy over the changed files only:
   ```
   cp -r new_version/school/templates/sheets school-results/templates/
   cp new_version/school/static/css/result-samples.css school-results/static/css/result-samples.css
   ```
6. No new dependencies and no database migration this time:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**.
8. Test it: open a student's result with the **Clean Mid-Term Report** template — the
   "Highest" column should be gone. Then switch to **Continuous Assessment Dossier** with
   a passport photo set — the photo should sit cleanly in the identity section with no
   overlap into the assessment table below it.

## Still outstanding (next phases)

Executive Band and Compact Academic template fixes (need your description of what's
wrong — see above), print/PDF orientation + Fit to Page + font scaling, mobile
responsiveness pass, and hiding instructional text by default.
