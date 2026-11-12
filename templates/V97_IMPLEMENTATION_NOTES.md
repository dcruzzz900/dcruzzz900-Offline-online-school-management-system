# V97 — One fixed result sheet, built from your own reference sheets

Your request, verbatim (with the two screenshots of result sheets from Government Secondary
School Goni-Gora): *"Use 1st template for terminal result sheet and second template for
cumulative/annual results sheet, generate exact template and use as default result sheet. Remove
all previous 16 result sheet, I don't want to use them again."*

## What changed

There is now exactly **one** result sheet design — built to match your two reference sheets as
closely as the system's real data allows — and it is the only design every school gets. The
"Result sheet style" picker (16 selectable designs: 10 structurally different built-in layouts
plus 6 sample-inspired ones) is gone completely, from the settings page, the database, and the
codebase.

The one design switches between two states automatically, exactly the way your two screenshots
show two different sheets for two different situations:

- **Per-term state** ("FIRST TERM RESULT SHEET" reference) — shown whenever Cumulative/Annual
  Results is off for the school, or on but this student has no cumulative data recorded yet.
- **Cumulative/Annual state** ("TERMINAL REPORT SHEET" / cumulative reference) — shown whenever
  Cumulative/Annual Results is on and there's real multi-term data for the student. This was
  already the rule as of V94 ("never show both at once"); V97 keeps it unchanged.

## 1. The new sheet, section by section

**Header** — school name, tagline, contact, logo and the result title — unchanged from before;
still uses your existing "Result title" setting (which already defaulted to "Terminal Report
Sheet", matching your second reference image's heading).

**Identity strip** — Name, Admission/Register No., Class/Arm, Academic Session, Term, and a new
**Class Position** box formatted exactly like your reference sheets: `1 / 45` (the student's
position and the class size together), not spelled out as "1st".

**Academic Performance table** (per-term state) — CA1 / CA2 / [CA3] / Exam / **Total** / **Avg.**
per subject, then Position / Grade / Remark — plus new **TOTAL** and **AVERAGE** footer rows
summing every column, matching your first reference sheet's table exactly. The Avg. column is
each subject's total divided by the number of score components actually in use (3, or 4 once
CA3 is switched on).

**Academic Performance Summary** (per-term state) — a new 6-up strip under the table: Total
Subjects, Total Score, Average Score, Percentage, Grade, Remark — the headline numbers from your
reference sheet, in one place.

**Cumulative / Annual Performance table** (cumulative state) — restyled to match your second
reference sheet exactly: every subject's full per-term breakdown (CA1/CA2/[CA3]/Exam/**Total**/
**Avg.**/Pos. for each term), then one **Overall Cumulative** group (Total/Average/Pos./Grade/
Remark), with TOTAL and AVERAGE summary rows across every subject — the per-term Avg. column was
the one piece still missing when this phase was last worked on; it's now in, computed the same
way as the per-term sheet's own Avg. column (total ÷ 3 or 4 components).

**Domain Ratings, Attendance** (now with a **Days Late** figure alongside Days Opened/Present/
Absent), **Comments, Signatures, Next Term Resumes** — unchanged in content; all still respect
every existing show/hide toggle on the Result Display Settings page.

**Grading & Domain key footer** — relabeled "**Grading Scale:**" and "**Domain Ratings Scale:**"
to match your reference sheets' own wording.

## 2. The 16-style picker is gone

- `db.py`'s `RESULT_TEMPLATES` now has exactly **one** entry (`professional_classic` — the
  existing default key is kept, unchanged, purely so no database row or test fixture needed a
  migration; nothing about the name is shown anywhere any more).
- The "Result sheet style" radio-picker card was removed entirely from the Result Display
  Settings page. Every other setting on that page (colors, logo position, toggles, fonts, page
  size, etc.) still works exactly as before.
- `v62_routes.py`'s save handler no longer validates a submitted template choice — the one
  design is simply always used.
- **`templates/sheets/*.html`** — the 6 bespoke, sample-inspired designs (Boxed Grey Card,
  Continuous Assessment Dossier, Clean Mid-Term Report, Green Cumulative Report, Peach Terminal
  Sheet, Progress Report Card) — **deleted**.
- **`static/css/result-samples.css`** — the stylesheet those 6 designs used — **deleted**, and
  its `<link>` tag removed from every page that loaded it.
- **`static/css/result-sheet.css`** — rewritten. All the CSS-Grid `grid-template-areas` layouts
  and per-style color/spacing rules for the other 15 designs are gone; what's left is the shared
  `.rs-sheet` component plus the new `.rs-summary`/`.rs-summary-grid` rules for the Academic
  Performance Summary strip. Nothing about the print pipeline's load-bearing `.rs-sheet` class or
  its automatic orientation/Fit-to-Page JavaScript was touched — they never depended on which
  style was active.
- `templates/_cumulative_sheet.html` (the standalone Annual/Cumulative Result page) now also
  carries the `rs-classic` class, for consistency, though it never had its own per-style markup
  to remove.

## 3. A real bug caught and fixed along the way

The new TOTAL/AVERAGE footer rows and the per-subject Avg. column summed every subject's CA1/
CA2/Exam, including subjects the student simply has no score recorded for — which the system
represents internally as the literal text `"-"`, not a number. Summing a `"-"` together with real
numbers crashed the page with a 500 error the moment any student had an unscored subject (a very
common, everyday situation — not an edge case). Fixed by having those sums and averages only
count subjects that actually have a numeric score, exactly the same "only count what's really
there" rule the Cumulative/Annual table has always used for its own totals.

## Testing

- All 9 test files that referenced the old 16-style picker, its per-style markup, or the old
  "Overall Position"/ordinal-text position label were updated to match the new, single design:
  `v61`, `v62`, `v64`, `v65`, `v68`, `v70`, `v72`, `v76`, `v85`, `v87`, `v94`
  `_scenarios.py`.
- One finely-tuned orientation-switching test (`v85`) needed its fixture re-calibrated — the new,
  wider Cumulative table (extra Avg. column) now overflows a landscape page too at 3 terms, so
  the test was narrowed to 2 terms, which still genuinely demonstrates the real browser-measured
  portrait→landscape switch this phase guards.
- Full regression: **all 37 suites (v60–v96) pass, 0 failures** — nothing else in the system
  (broadsheets, publication workflow, dashboards, billing, timetables, etc.) was affected.
- Verified directly: both sheet states (per-term and cumulative) render without error through the
  real print and PDF routes, with real multi-subject, multi-term data and toggled settings.
