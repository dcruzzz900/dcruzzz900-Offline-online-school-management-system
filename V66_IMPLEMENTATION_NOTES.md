# V66 — flexible score weighting (phase 1 of the full requirements doc)

This is the first of several planned phases against the full "Functional and
UI/UX Requirements" document. It covers P1 item 2 (flexible score weighting)
only — P0 was audited first and confirmed already working (AI consent,
draft saving, duplicate fields, migration backups, tenant isolation all
checked out against the live v65 code, nothing to fix there). The rest of
the document (Result Display Settings consolidation, Next Term Resumes,
Domain Ratings, approval permissions, templates/printing/fonts, etc.) is
still outstanding and will come in the next phases.

## What changed

**Grading Setup (`/admin/grading`) no longer permanently refuses a lower
CA1/CA2/CA3/Exam maximum just because a saved score already exceeds it.**

Before: saving `CA1 = 10` when any student already has a saved CA1 score of
20 was flatly refused with "CA1 maximum can't be lowered to 10: a saved
score is already 20." — with no way forward short of editing the max back
up.

Now:
1. Saving still fails outright only for things that are always wrong: a
   negative maximum, or maximums that add up to more than 100.
2. If the new maximums would leave some saved scores above the new limit,
   nothing is saved yet. Instead you see exactly which scores are affected
   — student, admission number, class, subject, session/term, and the saved
   value, broken down by component (CA1/CA2/CA3/Exam), up to 50 rows with a
   true total count if there are more.
3. You explicitly confirm ("I've reviewed the affected scores... apply
   anyway") to proceed. The scores themselves are never capped, deleted, or
   rewritten — they're left exactly as entered, and will simply display as
   exceeding the new maximum until a teacher corrects them (or you raise the
   maximum again).
4. Every change — old maximums, new maximums, who made the change, when, and
   how many scores were left affected — is recorded in a new
   `grading_config_audit` table and shown in a "Recent weighting changes"
   list at the bottom of the Grading Setup page.
5. Raising a maximum (or changing it with no conflicting scores) still saves
   immediately, no review step.

CA3 continues to be optional (max = 0 means off); switching it off never
deletes CA3 scores already saved, and switching it back on brings them
back into view. This was already true in v65 and is unchanged.

## Why historical results are unaffected

Scores are stored and summed as entered — a student's total is literally
CA1 + CA2 + CA3 + Exam, and grades come from the grade-scale bands applied
to that total. Neither depends on the current CA1_max/CA2_max/etc. at
render time, so changing the weighting later does not alter the totals or
grades of previously published results, broadsheets, or PDFs — they were
computed from the raw scores, not recalculated from the maximums.

## Database changes

One new migration step (`grading_config_audit_v66`) runs automatically the
first time the updated app starts — it only adds a new, empty
`grading_config_audit` table. As always, the app backs up `instance/school.db`
automatically before running any migration.

## Files changed

`db.py` (`grading_problems` now only covers negative/over-100; new
`grading_affected_scores` and `record_grading_config_change`; new migration),
`app.py` (`admin_grading` route rewritten for the review/confirm flow),
`templates/admin_grading.html` (review panel + recent-changes history).

## Tests

New `tests/v66_scenarios.py` / `tests/test_v66_behavior.py` — 17 checks:
review shown instead of refusal, score untouched while under review,
confirm applies the maximum and preserves the score exactly, audit row
written with old/new values + affected count, negative/over-100 still
refused outright, raising a maximum needs no review, CA3 on/off preserves
data, another school's config is untouched. Full existing suite re-run:
v63 (107), v64 (116), v65 (235) — all still pass, no regressions.

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
   cp new_version/school-results/templates/admin_grading.html school-results/templates/admin_grading.html
   ```
6. No new dependencies — reload isn't blocked on `pip install`, but it's
   safe to run anyway:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**. The new table is created
   automatically on the first request.
8. Test it: go to **Grading Setup**, lower a maximum below a score you know
   is on file — you should see the review list, not a hard refusal; tick the
   box and apply; confirm the "Recent weighting changes" entry appears and
   the score you saw in the review is unchanged in Score Entry.

## Still outstanding (next phases)

Everything else in the requirements document: admin-wide AI consent
management, Result Display Settings consolidation (incl. removing the
Cumulative/Annual card from Sessions & Terms), Next Term Resumes
toggle/date logic, annual/cumulative calculation review, Domain Ratings
rename + combined key, drafts/approval/publish permission separation,
template fixes (Executive Band, Compact Academic, Clean Mid-Term,
CA Dossier), orientation + Fit to Page + font scaling, mobile
responsiveness pass, and hiding instructional text by default. Tell me
which to do next.
