# V76 — Executive Band, Compact Academic & Vibrant Cards: your screenshot feedback

Your message, with the three screenshots of the Result Display Settings preview:

> "Too much empty white space on the result sheet of Executive Band, Compact Academic and
> Vibrant Cards. Remove double Domain rating (1 = Poor · 2 = Fair · 3 = Good · 4 = Very Good ·
> 5 = Excellent) on Psychomotor Domain and Affective Domain card on result sheet. In domain
> rating leave the numbers and remove this (e.g Emotional Stability 4 and remove Very Good)."

That's exactly the description I'd been waiting on since V72 — thank you. Two real, separate
fixes went in.

## 1. Domain rating shown twice per row — now just the number

Every domain rating row (Punctuality, Neatness, Emotional Stability, etc.) was showing the
rating **twice**: the number, and then the word it maps to right next to it — "4 – Very
Good". That's the "double Domain rating" you flagged. Fixed: each row now shows only the
number, e.g. "Emotional Stability **4**". Nothing else changed — the "Domain ratings: 1 =
Poor · 2 = Fair · 3 = Good · 4 = Very Good · 5 = Excellent" key at the bottom of the sheet
(which explains what the numbers mean) is untouched, since you only asked to remove the
repeated word next to each individual rating, not the one-line key itself.

This is in the single shared result-sheet component every template is built from, so it's
fixed everywhere — all 10 templates, preview, on-screen print and PDF alike (they all render
from the exact same HTML, by design since V64/V65).

## 2. Too much empty white space (Executive Band, Compact Academic, Vibrant Cards)

I read the actual CSS layout rules for these three templates rather than guess, and found the
real cause — not a bug exactly, but a layout mismatch:

All three arrange their sections in a CSS grid with a narrow "rail" (student info, attendance,
domain ratings) running beside a much taller block (the subjects table, or the comments box).
Where a short rail item shared a *row* with that taller block, the grid stretched the row to
match the tall block's height — and since the rail item itself has no visible box or border,
that stretch rendered as plain, invisible empty space underneath it. That's what you were
seeing: domain cards, attendance, or student-info blocks with a lot of dead air beneath them.

**Fix:** reshaped the layout (CSS grid-area assignments only — no visual restyling, no colour
or font changes) so a short rail item is never left alone in a row next to something much
taller:
- **Compact Academic** — the subjects table now runs beside the *whole* sidebar (student
  info, attendance, domain ratings, grading key) instead of just two of those four items;
  comments and signatures now sit in their own full-width rows below.
- **Executive Band** — same idea: the subjects table now runs beside the entire right-hand
  rail (student info, domain ratings, attendance, key), and signatures get their own
  full-width row instead of being squeezed beside the key.
- **Vibrant Cards** — domain ratings, attendance and comments now sit as three side-by-side
  cards in a single row (which also suits the template's own "cards" look better) instead of
  comments spanning two rows against two much shorter neighbours.

One honest caveat: a 2-column "narrow rail beside a big table" layout will always have *some*
natural height difference between the two sides — that's inherent to the design, not a bug,
and no layout trick removes it entirely without breaking the look. What this fix removes is
the *extra*, avoidable inflation that came from mismatched row-pairings; I verified the result
by actually rendering all three templates in a real browser and measuring their rendered
height against a baseline template using the same data (details under Tests below), not just
by reading the CSS and assuming it would look right.

## Files changed

- `templates/_result_sheet.html` — removed the per-row word-label span from the domain rating
  cell (fix 1; affects all templates since they share this file).
- `static/css/result-sheet.css` — reshaped `grid-template-areas` for `.rs-compact_academic`,
  `.rs-executive_band` and `.rs-vibrant_cards` only (fix 2). No other template touched.

## Database changes

None.

## Tests

New `tests/v76_scenarios.py` / `tests/test_v76_behavior.py` — 34 checks:

1. **Domain rating rendering** — across 5 templates (including Executive Band, Compact
   Academic, Vibrant Cards and two others, to confirm the shared-component fix reaches every
   template): each row shows only the number, the bottom "Domain ratings:" key line is still
   present and unchanged, the "Domain Ratings" section heading appears exactly once (never
   duplicated per card), and both domain group labels (Affective Domain / Psychomotor Domain)
   each appear exactly once. Verified against **real domain-rating data** seeded into the test
   database (skill traits + per-student ratings), not just the admin preview's sample data, so
   this checks what actually prints and goes into the PDF.
2. **Grid layout source checks** — confirms the subjects table now spans the entire sidebar in
   Compact Academic and Executive Band (not just part of it), that comments/signatures are no
   longer paired against a narrower neighbour, and that Vibrant Cards' three sections sit
   side by side in one row rather than one spanning two rows against shorter neighbours.
3. **Live rendering checks** — starts a real Flask server, drives a real headless Chromium
   browser, logs in, and for each of the three templates renders the real `/result/.../print`
   page with real seeded data, resets any shrink-to-fit zoom the page's own script applies,
   and measures the sheet's true unscaled content height. Confirms none of the three is
   inflated more than 1.6× a `professional_classic` sheet built from identical data — a
   regression-safe comparative check (this is the same "render for real and measure" approach
   used for the V75 responsiveness fix, since a plain HTTP fetch can't detect a CSS-grid
   layout defect — the HTML is identical whether it's broken or fixed).

Full existing suite re-run: v60 (213), v61 (292), v62 (238), v63 (107), v64 (116), v65 (235),
v66 (17), v67 (13), v68 (12), v69 (20), v70 (39), v71 (30), v72 (9), v73 (30), v74 (21), v75
(7) — all still pass, no regressions. **1,433 checks total across the whole suite, 0 failed.**

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
5. Copy over the two changed files:
   ```
   cp new_version/school/templates/_result_sheet.html school-results/templates/_result_sheet.html
   cp new_version/school/static/css/result-sheet.css school-results/static/css/result-sheet.css
   ```
6. No new dependencies and no database migration this time:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**.
8. Test it: open **Result Display Settings**, switch the template through Executive Band,
   Compact Academic and Vibrant Cards in turn, and confirm (a) each domain rating row shows
   just a number, with no "– Very Good" style text next to it, and (b) the sheets look
   noticeably tighter, without the big blank gaps below the domain/attendance/info cards.

## Where this leaves things

This closes out the Executive Band / Compact Academic item that's been open since V72, plus
the newly-named Vibrant Cards issue — the only outstanding item from the eighth requirements
document is gone. If you'd like the consolidated final report (completed requirements,
outstanding issues, every test performed, full migration/deployment history) now that
everything is done, just say so.
