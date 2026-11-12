# V100 — One sample design for screen, Print and Download; cumulative fits A4 portrait; full domain list

Your request: the "Updated Terminal Report Sheet" sample (photo 1) must be the design on BOTH the
print interface and the download; the Cumulative/Annual card must fit A4 portrait/the screen without
cutting off Remark; Download must match Print; every Affective/Psychomotor item on the sample must be
captured and selectable like the others.

## 1. Sample design everywhere
`static/css/result-sheet.css` rewritten to the sample: navy headings, pale-blue section banners, rounded
pale-blue boxes (identity, attendance, comments), Class Position taking the rest of row two, a 6-up
summary strip with big values, side-by-side Domain tables with a "Rating" header, one signature line,
two-column grading/domain key. Tints derive from the school's Second colour (sky blue by default).
New defaults: Main #0b2a6f, Second #29a9e0. Migration 074 moves only schools still on the OLD built-in
defaults (#1f3a5f / #c9a227); a colour a school chose itself is untouched.

## 2. Cumulative / Annual table fits A4 portrait and the screen
* Root cause on phones: the sitewide `table{display:block}` rule (responsive-ui.css, ≤700px) destroyed
  the table grid, so Subject collapsed and Remark was pushed out of view. Sheet tables are now always
  real tables.
* The table uses `table-layout:fixed` with a `<colgroup>` computed from the number of terms (and CA3), so
  it is exactly the sheet's width on any term count; Remark can no longer be clipped.
* The cumulative state is always A4 **portrait** (no auto-landscape). When a sheet must shrink, its layout
  width is widened by 1/zoom so it still fills the page width (no strip, no clipping).
* On phones the table is laid out at real A4 width and scaled to the screen (`static/js/result-fit.js`).

## 3. Download = Print
Downloads are the print page printed by Chromium. On hosts where Chromium can't run (your phone's
download in photo 3 came from this fallback) the system used an older, different reportlab layout. New
`pdf_sheet.py` draws the same sample design — including the Cumulative/Annual table (all terms, Remark),
summary, domains, signatures and keys — and is used by the per-term, class-bundle and dedicated
cumulative PDFs.

## 4. All sample domain items
Affective (8): Emotional Stability, Honesty, Leadership, Neatness, Punctuality, Relationship with Others,
Attitude to Work, Cooperation. Psychomotor (7): Club & Societies, Handling of Tools, Handwriting,
Sports/Games, Drawing Skills, Practical Skills, Physical Coordination.
New schools get all 15; migration 073 adds the missing ones to existing schools as active traits (they
appear in Update Result Details and Domain settings, can be renamed/deactivated like any other). Existing
items are never renamed/removed; sample order applied only where a school never re-ordered. The settings
live preview shows the full list.

## Tests
`tests/v100_scenarios.py` (25 checks, both Chromium and fallback PDFs). Existing suites v60–v96 pass;
assertions that pinned old behaviour were updated (auto-landscape for cumulative, "Scale:" colon,
passport/logo CSS values).
