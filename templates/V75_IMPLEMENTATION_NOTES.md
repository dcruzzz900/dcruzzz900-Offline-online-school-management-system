# V75 — Mobile/tablet/desktop responsiveness pass

Eleventh and final phase against the full "Functional and UI/UX Requirements" document:
"mobile/tablet/desktop responsiveness pass." This closes out everything from that document —
see the bottom of this file for the consolidated status of all P0-P3 items.

Executive Band and Compact Academic (the two template fixes from V72's queue) are still
waiting on your description or screenshot of the actual problem — this phase doesn't touch
them.

## What I found before changing anything

I audited the app shell, global CSS breakpoints, and a sample of heavy pages (dashboard, a
data table, settings, auth) before writing any code, same as the V72/V74 "don't guess-fix,
verify first" approach. The honest finding: **the app shell already has working responsive
navigation** — a sidebar that collapses to a hamburger-toggle menu, viewport meta tags
present on every page, and existing `@media` breakpoints already handling grids/tables in
most places. This is not a "build mobile support from scratch" situation.

But one real, concrete defect turned up, and I verified it the same way the result-sheet
templates got verified in V72: **by actually rendering the page in a real headless browser**
at a sweep of viewport widths and reading the computed CSS, not by reading the stylesheet and
guessing. (A plain HTTP fetch can't catch this kind of bug — the HTML is byte-identical
whether it's broken or fixed; only what the browser computes from the CSS cascade differs.)

**The bug:** three `@media` rules across `static/css/style.css` (two, from different revision
eras of the file) and `static/css/ai-ui.css` all control the same sidebar-collapse behavior,
and they'd drifted to two different breakpoint values — 1050px in one place, 1000px in the
other two. The browser measurement showed exactly what that drift does in practice:

| viewport width | sidebar | hamburger button |
|---|---|---|
| 1060px (above both) | visible, fixed in place | hidden (correct — desktop) |
| **1040px / 1024px / 1010px** | **collapsed off-screen** | **hidden** |
| 1000px and below | collapsed off-screen | visible (correct — tap to reopen) |

In the 1001-1049px range — which includes **1024px, the standard tablet-landscape width** —
the sidebar collapses itself off-screen (because the 1050px rule fires) but the button that
would bring it back stays hidden (because a later, unconditional rule in `ai-ui.css`, loaded
after `style.css`, resets it to `display:none` outside its own 1000px media query). The
result: on a tablet in landscape at that width, there was no way to reach the app's
navigation at all without manually resizing the browser window — a real dead end, not a
cosmetic issue.

## What changed

One line: `static/css/style.css`'s drifted `@media(max-width:1050px)` sidebar-collapse rule
is now `@media(max-width:1000px)`, matching the other two. All three sidebar-collapse rules
in the app now agree on exactly one breakpoint, so there's no gap for navigation to fall into
— verified by re-running the same browser measurement across 16 widths (900-1300px,
including every width that was previously broken) and confirming the sidebar is never
off-screen while its reopen button is simultaneously hidden, at any width, plus confirming
clicking the button actually opens the sidebar at mobile/tablet widths.

I deliberately did **not** rewrite or consolidate the surrounding CSS further (there are
other redundant/overlapping rule blocks left over from past revisions, e.g. `.app-sidebar` is
defined twice with slightly different widths in `style.css`) — those are untidy but not
broken, and rewriting working CSS "for cleanliness" risks introducing a new regression for no
functional benefit. This phase fixes the one thing that was actually, verifiably broken.

## Why I didn't change anything else

Everything else the audit looked at was already working as intended, or already has sensible
mobile handling that this phase would just be duplicating:

- Every data table already gets automatic horizontal-scroll handling on narrow screens (a
  sitewide `table{display:block;overflow-x:auto;white-space:nowrap}` rule at the 700px
  breakpoint), and several pages additionally use a `.table-wrap`/`.responsive-table`
  card-flip pattern for an even better small-screen table layout. No page was found missing
  both.
- The `<meta name="viewport">` tag is present on every page template (either inherited from
  `base.html`, or set directly on the handful of standalone pages like the print views and
  the billing-audit tool).
- The hardcoded-column CSS grids flagged in the audit (`.stat-grid`, `.card-grid`,
  `.ai-grid`, etc.) all already have matching mobile overrides collapsing them to 1-2 columns
  at the existing breakpoints — they're just not written with `auto-fit`/`auto-fill`, which
  is a style preference, not a responsiveness defect.
- The super-admin shell's own nav-collapse toggle (`.platform-nav-toggle`, 820px breakpoint)
  was checked the same way and found internally consistent — no drift there.

## Files changed

`static/css/style.css` (one breakpoint value, plus an explanatory comment).

## Database changes

None.

## Tests

New `tests/v75_scenarios.py` / `tests/test_v75_behavior.py` — 7 checks, in two parts:

1. **Static checks** — confirms the drifted 1050px rule is gone and every remaining
   sidebar-collapse `@media` rule across `style.css` + `ai-ui.css` now uses the same value.
2. **Live rendering checks** — starts a real Flask server, drives a real headless Chromium
   browser through Playwright, logs in, and sweeps 16 viewport widths (every width that was
   previously broken, plus boundary and control values), reading the actual computed
   `display`/`transform` CSS values at each one. Confirms the sidebar is never left
   off-screen with its reopen button also hidden at any width; confirms clicking the
   hamburger button actually opens the sidebar (not just that the CSS looks right) at mobile
   (375px), tablet (768px/1000px) widths; confirms desktop (1300px) is unaffected.

This is the first browser-rendering (as opposed to HTTP-request) test in this suite, because
this specific bug is invisible to one — it only exists in the browser's computed CSS, not in
the HTML response.

Full existing suite re-run: v60 (213), v61 (292), v62 (238), v63 (107), v64 (116), v65 (235),
v66 (17), v67 (13), v68 (12), v69 (20), v70 (39), v71 (30), v72 (9), v73 (30), v74 (21) — all
still pass, no regressions. 1,399 checks total across the whole suite, 0 failed.

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
5. Copy over the one changed file:
   ```
   cp new_version/school/static/css/style.css school-results/static/css/style.css
   ```
6. No new dependencies and no database migration this time:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**.
8. Test it: on a tablet, or a desktop browser window resized to roughly 1024px wide, confirm
   the sidebar collapses and the ☰ button in the top bar reliably opens it back up — that
   exact width used to leave you stuck with no way to reach the menu.

## Where this leaves the full eighth requirements document

With this phase, every item from the eighth "Functional and UI/UX Requirements" document is
either built and tested, or explicitly handed back to you with a specific question:

- **Built across v66-v75**: flexible score weighting, AI consent bulk management, Result
  Display Settings consolidation + Next Term Resumes, annual/cumulative ranking consistency,
  Domain Ratings rename + combined grading key, draft/approval/publish permission separation
  (and its one real gap, in `save_score`'s audit trail), two of four template fixes (Clean
  Mid-Term "Highest" column, CA Dossier passport overlap), print/PDF orientation + Fit to
  Page + font scaling, instructional-text hide-by-default, and this phase's responsiveness
  fix.
- **Still waiting on you**: Executive Band and Compact Academic template fixes — audited
  twice now (V72 and again implicitly while scoping this phase) with nothing obviously wrong
  found either time, so I need a description or screenshot of the actual visual problem
  before I can fix the right thing rather than guessing.

A consolidated final report (completed requirements, outstanding issues, every test
performed, and the full migration/deployment history) is ready whenever you want it — just
say so, or let me know once Executive Band/Compact Academic are squared away and I can fold
that in too.
