# V68 — annual/cumulative calculation correctness (phase 3 of the requirements doc)

Third phase against the full "Functional and UI/UX Requirements" document,
covering P1 item 5: reviewing the annual/cumulative calculations for
correctness.

## What was found

Auditing the class-ranking code turned up a real inconsistency, not a
missing feature: **"Overall Position" — on the term broadsheet, the
annual/cumulative broadsheet, and the "Overall Position" shown on a
student's own result sheet — was computed with a plain sequential count
(1, 2, 3, 4…), while the subject-level positions shown right next to it on
the same sheet were already computed with standard competition ranking
(1, 2, 2, 4…, where tied students share a position).

In practice this meant two students with the *exact same total score* could
see, on the very same result sheet, their shared subject position correctly
shown as "1st" for both — but their class-wide "Overall Position" shown as
"1st" for one and "2nd" for the other, for no reason a parent or teacher
could explain by looking at the numbers.

## What changed

A single ranking rule (standard competition ranking: ties share a position,
and the rank after a tie jumps to the student's actual place rather than
just counting the tie as one slot) is now used everywhere a class is
ranked by a score or average:

- The term broadsheet (`/broadsheet/<class_id>`)
- The annual/cumulative broadsheet (`/cumulative/<class_id>`)
- The "Overall Position" shown on every result sheet and PDF (which reuses
  the term broadsheet's ranking under the hood)
- The cumulative/annual result view for an individual student (which
  reuses the cumulative broadsheet's ranking)

This now matches the subject-level position logic (`compute_subject_positions`),
which already used this convention — so a result sheet can never again show
a tie at the subject level and a broken tie at the class level for the same
two students.

When there's no tie, nothing changes: positions are still exactly 1, 2, 3…
as before.

## Why this doesn't touch totals or grades

This is purely a ranking/position change — it doesn't touch how a total,
average, or grade is computed. Scores are still summed as entered and
grades still come from the grade-scale bands, so no student's total,
average, or grade on any existing or historical result changes. Only how
two (or more) *equal* results are placed relative to each other changes.

## Files changed

`app.py` — new shared `rank_with_ties()` helper; `build_broadsheet_data`
(term broadsheet / result-sheet "Overall Position") and
`build_cumulative_broadsheet_data` (annual/cumulative broadsheet) both now
call it instead of a plain enumerate-after-sort.

## Database changes

None. No migration — this only changes how existing data is ranked for
display, nothing is stored differently.

## Tests

New `tests/v68_scenarios.py` / `tests/test_v68_behavior.py` — 12 checks:
two students tied for the top total share position 1 on the term
broadsheet (not 1st/2nd); the third, clearly-behind student correctly
shows position 3, not 2; each tied student's own result sheet shows the
same "1st" Overall Position, matching their already-tied subject position;
an untied case still ranks strictly 1, 2, 3 (no regression); the
annual/cumulative broadsheet produces a genuine tie correctly, and a
near-tie that isn't actually equal is NOT falsely tied. Also added missing
pytest wrappers `tests/test_v67_behavior.py` (the v67 phase had scenarios
but no wrapper yet). Full existing suite re-run: v60 (213), v61 (292), v62
(238), v63 (107), v64 (116), v65 (235), v66 (17), v67 (13) — all still
pass, no regressions. 1,243 checks total across the whole suite, 0 failed.

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
5. Copy over the changed file:
   ```
   cp new_version/school-results/app.py school-results/app.py
   ```
6. No new dependencies, and no database migration this time — just:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**.
8. Test it: give two students in the same class identical total scores for
   a term, then open the class broadsheet — both should show the same
   position number, and the next student down should skip ahead
   accordingly (e.g. 1, 1, 3 — not 1, 2, 3). Check their result sheets show
   the same "Overall Position" as each other.

## Still outstanding (next phases)

Domain Ratings rename + combined grading key display, draft/approval/
publish permission separation (gap-closing pass), template fixes
(Executive Band, Compact Academic, Clean Mid-Term — incl. removing its
"Highest" column, Continuous Assessment Dossier passport positioning),
print/PDF orientation + Fit to Page + font scaling, mobile responsiveness
pass, and hiding instructional text by default. Tell me which to do next.
