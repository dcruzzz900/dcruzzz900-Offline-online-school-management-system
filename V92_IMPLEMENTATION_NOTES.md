# V92 — Result Display Settings: Paper Sizes (Phases 6-7)

Phases 6 and 7 of your "Complete Feature Enhancement Specification" document, delivered together
since they're really one change: a configurable paper size, and the automatic layout/print/PDF
pagination that has to follow it.

## What's in this round

**A new Paper Size control** in Result Display Settings, next to the existing Page Orientation
setting (they're independent of each other):

- **A4** (the default — unchanged for every school that never opens this setting)
- **A3**
- **A5**
- **Letter** (8.5" × 11")
- **Legal** (8.5" × 14")
- **Foolscap** (8.5" × 13", the size commonly used in Nigeria)
- **Custom** — type any width/height in millimetres (50mm–1200mm each). However you enter the two
  numbers, the narrower one is always treated as the portrait width — so entering them backwards
  doesn't produce a sideways page.

This applies to the **individual result sheet and the cumulative/annual result** — preview, print,
and the actual downloaded PDF, all three, the same way the project's "Preview = Print = PDF"
principle has always worked. **The broadsheet deliberately stays A4 landscape**, unaffected by this
setting (see "What I left out" below).

## How it works

Every paper size — the six built-in ones and Custom — boils down to the same two numbers: a width
and a height in millimetres, always stored portrait-first (the narrower figure is the width). A4 is
just 210×297; nothing else about the mechanism needed to change for it to generalize.

The existing V85 "Automatic" orientation mechanism (`decideOrientation()` — a genuine rendered-
height measurement at both page widths through the same Chromium pipeline that builds the PDF, not
a guess) and the V73/V79 one-page fit-and-shrink mechanism (`fit()`) were both hardcoded to
A4's 210mm/297mm. V92 made both read the configured size instead — nothing about *how* they decide
or shrink changed, only *which numbers* they're deciding and shrinking against. The same is true of
the `@page` CSS rule that actually controls what size Chromium prints: it now writes the width and
height explicitly (`@page{size:420mm 297mm}`) instead of a size keyword (`@page{size:A4 landscape}`)
— a small change that's what makes the same one rule work for every paper size instead of needing a
special case for each one.

## What I left out, and why

- **The broadsheet stays A4 landscape.** It's a whole-class grid, not a single student's result —
  Result Sheet Configuration in your document reads as being about the individual result, and a
  class of 40+ students already strains A4 landscape's width; letting it follow a school's result-
  sheet paper size (which might be A5, say) would make it actively worse, not better. If you'd like
  the broadsheet to have its own, separate paper-size setting, that's a small, well-scoped follow-up
  — just say so.
- **No per-size margin control.** Every size uses the same `margin:0` the sheet's own CSS padding
  already provides (10mm, inside the page) — consistent with how A4 has always worked here, and
  simplest for a first pass. A separate per-size margin setting is easy to add later if it turns out
  to matter for, say, Foolscap paper that a school's printer handles slightly differently.
- **Custom size has no live preview thumbnail of the paper shape itself** (just the width/height
  number fields) — the full-size live preview further down the settings page already reflects
  whatever is typed in once saved, which covers the same need.

## Database changes

One small, additive migration: `result_display_settings` gains `paper_size` (defaults `'A4'`),
`custom_width_mm`, and `custom_height_mm` (both nullable, only read when `paper_size='Custom'`).
Every existing school's row gets `paper_size='A4'` automatically — nothing changes for anyone until
an admin opens this setting and picks something else.

## Testing

- New suite `tests/v92_scenarios.py` (16 checks, all passing) — and these check the **real,
  downloaded PDF's actual page dimensions** (read back out of the PDF bytes with `pypdf`), not just
  the HTML, so this is verified all the way through the pipeline you'd actually use:
  - A school that never touches the setting still gets an exact A4-portrait PDF.
  - Switching to A3 + Landscape is saved, and the next PDF downloaded is genuinely 420×297mm.
  - The cumulative result print page picks up the same size.
  - Custom dimensions entered backwards (wider-first) are normalized and still produce a correctly-
    shaped PDF.
  - An out-of-range custom size is refused with nothing silently saved, and the previous valid
    custom size is left untouched.
  - Letter, Legal, Foolscap and A5 all produce a PDF of the exact right size.
  - Tenant isolation: one school's chosen paper size never affects another school's.
- Found and fixed one real regression while finishing this round: two long explanatory HTML
  comments I'd added pushed enough extra (but non-differentiating) text into the first 1200
  characters of the rendered page that an existing V65 test — which checks that the 6 result-sheet
  template styles still produce 6 genuinely different layouts — could no longer tell two of them
  apart within that window. Fixed by trimming the comments, not by touching the template markup
  itself; re-ran that suite to confirm all 6 styles are still distinct.
- Updated two other existing tests whose assertions were tied to the *old* literal `@page{size:A4}`
  / `@page{size:A4 landscape}` text, which this round intentionally changed to explicit
  `@page{size:210mm 297mm}` dimensions (same real page size, new, more general format) — the same
  "fix a stale literal-text assumption, don't weaken the check" pattern used for similar cases in
  earlier rounds (v65, v80).
- Full regression run: **all 33 test suites (`tests/v60_scenarios.py` through
  `tests/v92_scenarios.py`), 1,795 checks total, 0 failures.**

## Installing on PythonAnywhere

This round adds 3 new columns, so please back up first:

```bash
cd ~/school-result-system
cp main.db main.db.bak-v92
```

Then:
1. Replace the changed files (or extract the new zip over your install): `app.py`, `db.py`,
   `v62_routes.py`, `templates/result_display_settings.html`, `templates/result_print.html`,
   `templates/cumulative_result_print.html`.
2. Reload your web app from the **Web** tab — the migration runs automatically on first request.
3. Open **Result Display Settings** and confirm the new **Paper Size** dropdown appears (defaulted
   to A4), with width/height fields that appear only when you choose Custom.
4. Pick A3, save, and open a result's **Download PDF** — confirm the PDF is genuinely the new,
   larger size, not just the on-screen preview.
5. Try Custom with a couple of mm values, and try Automatic orientation with a non-A4 size to
   confirm it still picks whichever orientation needs less shrinking, same as it already did for A4.

## What's next

**Phase 8 — final cross-cutting verification pass** is the last item on the 10th requirements doc's
roadmap: a dedicated pass checking every phase from this document together (not in isolation),
looking specifically for interactions between them — e.g. a Student Dashboard's Academic
Performance chart printed at a non-A4 size, or a Recent Activities entry for a paper-size change
itself. Let me know if you'd like me to run that next, or if there's something else you'd rather
prioritize first.
