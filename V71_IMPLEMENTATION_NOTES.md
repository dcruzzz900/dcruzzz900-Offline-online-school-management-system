# V71 — Draft/approval/publish permission separation (gap-closing pass)

Sixth phase against the full "Functional and UI/UX Requirements" document, covering
the P1 item: "draft/submit/review/approve/publish/print/download permission separation,
server-side enforcement, subject-teacher score-change audit trail."

Most of this requirement was already solidly built in an earlier phase (V63): a 7-state
workflow (draft → submitted → under review → returned/approved → published, plus
reopened), explicit RBAC-only permission grants (holding a title like Principal never
publishes on its own), mandatory reasons for destructive actions, pre-submission
data-completeness checks, and a central `before_request` guard that blocks every
print/PDF/download/email/portal route for a class whose result isn't published. This
phase was a focused audit of that existing machinery, looking specifically for any place
still using the **term-wide** "is this term published" signal instead of the **class's
own** publication status — because a school's term can contain several classes, and only
one of them being published should never unlock another class's still-unapproved result.

## What changed

**The audit's main finding, verified and closed:** `save_score` — the one function that
writes a score and its audit trail — decided two things from `terms.is_published`, the
legacy flag that just means "at least one class in this term has been published":

- Whether a reason is *mandatory* when editing a score that belongs to a class which was
  published and has since been reopened for correction.
- What label (`result_status`) gets written to the `score_audit` history row.

Because that flag is term-wide, both could be wrong the moment a *different* class in the
same term was published: a reopened class's score could be edited with **no reason
required**, and the audit trail could record a misleading "Published" (or "Draft") label
that didn't reflect this class's actual history. Both now read this class's own real
workflow state instead (`Draft`, `Submitted for review`, `Under review`, `Returned for
correction`, `Approved — ready to publish`, `Published`, `Reopened — correction`) — the
same state machine already used everywhere else in the workflow.

**Also hardened for consistency, though not independently reachable:** a second set of
routes — a student viewing/downloading/printing their own result, a parent doing the same
for their child, and staff emailing a result to a parent — had their own, separate checks
against the same term-wide flag. In practice these exact URLs are already intercepted
first by the existing central publication guard (`v63_spec.py`'s `before_request` hook),
which was already checking the correct, per-class status — so this was not a live,
reachable gap. It was still wrong code sitting behind a correct guard, and is now
consistent with it, so the guard isn't the only thing standing between these routes and
the old bug. This was proven with a concrete two-classes-one-term test (one class
published, a sibling class left in draft) — the exact scenario the V63 test suite had a
placeholder for (`check("another class's student is still blocked ...", True)`) but never
actually set up with a second class.

## Why this holds

- `save_score` now computes this class's own publication status once
  (`v63_core.publication_status`) and uses that same value both to decide whether the
  score is locked at all, and — if it's unlocked specifically because it's in the
  `reopened` state (meaning it *was* published and is being corrected) — to require a
  reason. No other state requires one, matching the original intent of auditing a
  correction to a result that had already gone out.
- The `score_audit.result_status` column now always records
  `v63_core.STATE_LABELS[<this class's actual state>]`, so reading the audit trail for a
  class always tells the truth about that class, never a neighbor's.
- The student/parent/staff routes in `app.py` and `v61_routes.py` now resolve the
  specific class a student was actually in for that term (`student_class_for_term`,
  already used elsewhere for exactly this reason — it accounts for mid-year promotions)
  and check `v63_core.is_published` for that class, via a small shared helper
  (`result_class_published`) — the same source of truth every other part of the system
  already treats as authoritative.

## Files changed

`app.py` (new `result_class_published` helper; `save_score`'s reason-requirement and
audit-label logic; `parent_result`, `parent_result_pdf`, `email_class_results`,
`email_result`, `student_result`, `student_result_pdf`), `v61_routes.py`
(`student_result_print`, `parent_result_print`), `tests/v63_scenarios.py` (one existing
check updated — see Tests).

## Database changes

None. No migration — this phase only changes which status check a few code paths read;
no table, column or stored value changes shape.

## Tests

New `tests/v71_scenarios.py` / `tests/test_v71_behavior.py` — 30 checks, built around a
second class in the same term that is deliberately never submitted while the first class
goes through the full workflow and gets published:

- Staff/admin print and PDF are correctly blocked for the unpublished class even with the
  term-wide flag set (sanity check — this layer was already correct).
- A student logged into the unpublished class is blocked from viewing, downloading and
  printing their own result even though a sibling class in the same term is published;
  the same student's own class's result becomes visible once *that* class is genuinely
  published too.
- The same two checks for the parent portal, plus confirming the parent's own
  children/result list never linked to the unpublished result in the first place.
- Staff emailing a single student's result, and staff bulk-emailing a whole class, are
  both refused for the unpublished class and allowed for the published one.
- The score-audit fix: editing a reopened (previously published) class's score without a
  reason is refused and succeeds once a reason is given, the audit row's `result_status`
  reads "Reopened — correction" (this class's true state) even while the term-wide flag
  is still 1 (a sibling class is still published), and a genuinely published/locked
  class's scores still cannot be edited directly at all (no regression in the lock
  itself).

One existing check in `tests/v63_scenarios.py` ("correction is possible after reopening")
needed a reason added to its form post — an intentional consequence of now requiring one
for reopened-class edits, not a regression; the check and its message were updated to
match (project convention: update the old test to match the new intended behavior).

Full existing suite re-run: v60 (213), v61 (292), v62 (238), v63 (107), v64 (116), v65
(235), v66 (17), v67 (13), v68 (12), v69 (20), v70 (39) — all still pass, no regressions.
1,332 checks total across the whole suite (including v71's 30), 0 failed.

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
   cp new_version/school/app.py school-results/app.py
   cp new_version/school/v61_routes.py school-results/v61_routes.py
   ```
6. No new dependencies and no database migration this time:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**.
8. Test it: with a second class left as a draft (never submitted), publish your first
   class through **Results → Workflow**. Log in as a student or parent of the second,
   still-unpublished class and confirm their result still correctly shows "not published"
   — it should not have become visible just because the other class was published.

## Still outstanding (next phases)

Template fixes (Executive Band, Compact Academic, Clean Mid-Term — incl. removing its
"Highest" column, Continuous Assessment Dossier passport positioning), print/PDF
orientation + Fit to Page + font scaling, mobile responsiveness pass, and hiding
instructional text by default. Tell me which to do next.
