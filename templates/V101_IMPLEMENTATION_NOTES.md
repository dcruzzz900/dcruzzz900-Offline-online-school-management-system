# V101

## Passport
The photo now FILLS the passport frame (object-fit: cover, top-centred so faces stay in) and the frame has no border
line. Same in the fallback PDF (`_Cover` flowable: clipped, scaled to cover, no border).

## Result sheet follows Result Display Settings
Audit of every setting against the HTML sheet and the PDF fallback. Fixed: the "PDF / report font" now also drives the
on-screen/print sheet (it was hard-coded to Arial there); "Header text alignment" now also applies in the fallback PDF.
All show/hide switches, colours, header layout, signature layout, watermark, footer and next-term date are read by all
six designs on both render paths (tests/v101_scenarios.py switches them off and checks each design).

## Six selectable designs (Result Display Settings -> "Result sheet design", live thumbnails)
professional_classic (Classic Blue, the sample) - executive - minimal_line - sidebar_profile (two columns) -
dashboard_cards (KPI cards first, card grid) - bold_banner (gradient hero, pills, tiles).
Stored in result_display_settings.template; unknown values are refused. Sections are captured as blocks in
`_result_sheet.html` and arranged per design (linear / sidebar / cards); CSS in result-sheet.css; the reportlab
fallback (`pdf_sheet.py`, STYLES table) draws the same six so Download = Print on every host. The Cumulative/Annual
table keeps its fixed A4-portrait fit in every design (in the sidebar design it spans the full width).

## Domain ratings: tick-box table
Update Result Details now shows one table per domain, items down, 1-5 across (meanings in the legend/headers), a tick
box per cell; tick again to clear. Blank = no rating and now CLEARS an earlier rating on save. Fits a phone width.

## Submit for review / approve / publish
A class result needs only ONE saved score (any student, any subject) to be submitted, then reviewed, approved and
published. Scores that exist are still validated; none saved at all is still refused with a clear message.

## Form teachers saving with the Principal's comment shown
Saving no longer aborts when the Principal's (or teacher's) comment field is submitted by someone who may not edit it:
that field is ignored, the stored comment is kept, and ratings/attendance/etc. are saved.

## Tests
tests/v101_scenarios.py (62 checks). Existing suites pass; assertions pinned to the old single design / dropdown /
"contain" photo were updated (v62, v64, v65, v70, v72).
