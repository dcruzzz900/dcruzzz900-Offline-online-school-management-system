# V73 — Print/PDF page orientation, a "Fit to Page" toggle, and a font-size scale

Ninth phase against the full "Functional and UI/UX Requirements" document, picking up the
next item in the queue after V72's two deferred template items (Executive Band and Compact
Academic are still waiting on your description/screenshot — no update there this round).

## Architecture note (why this phase touches templates, not pdf_utils.py)

`app.py` overrides `pdf_utils.py`'s ReportLab PDF builders with Chromium-based ones that
render the exact same HTML used for on-screen print/preview — the project's own "Preview =
Print = PDF: the PDF is the print page, printed by Chromium" design. The ReportLab path is
only a fallback for a host with no Chromium installed. So the real surface for this phase is
`templates/result_print.html` (its inline `@page` CSS and `fit()` JS) and
`templates/broadsheet_print.html` — not `pdf_utils.py`.

## What changed

Three new, independent settings, added to the existing central Result Display Settings page
(admin → Result Display Settings → new "Page orientation" and "Print / PDF font size"
dropdowns, plus a new "Automatically Shrink to Fit One Page" switch alongside the other
ON/OFF toggles). Each is additive and **defaults to exactly today's behaviour** — a school
that never opens the new controls sees no change at all:

1. **Page orientation** (Portrait / Landscape) — the printed/PDF page size for the
   **individual result sheet**. Was hardcoded portrait everywhere; defaults to Portrait.
   Implemented as an inline `@page{size:A4 landscape;...}` override in `result_print.html`,
   layered after the stylesheet links so it wins. Broadsheets are a separate, always-landscape
   document and are **not** affected by this setting — it only changes the one-student sheet.
2. **Fit to Page** (ON by default) — exposes the sheet's always-on auto-shrink (the existing
   "if it's taller than one page, scale it down" logic) as an explicit, turn-off-able switch.
   Off, a sheet that's genuinely too long to shrink sensibly is left to flow onto a second
   page at full size instead of being squeezed small.
3. **Print / PDF font size** (Small / Normal / Large) — a flat zoom applied to the whole
   sheet. Templates use fixed point-size fonts (e.g. `font:10.5pt`), which don't scale from a
   parent `font-size` percentage, so this is done with CSS `zoom` (0.9× / 1.0× / 1.12×) —
   the same mechanism the auto-shrink already uses, so the two compose correctly: if a sheet
   still overflows after applying the chosen font size and Fit to Page is on, the auto-shrink
   ratio takes over and wins (a sheet already being shrunk to fit never gets blown back out
   past one page just because "Large" was picked). The broadsheet picks up the same font-size
   preference (composed with its own existing width-based auto-shrink); its orientation stays
   untouched (always landscape).

## Why this holds

- All three settings are additive columns with safe defaults (`page_orientation='portrait'`,
  `fit_to_page=1`, `font_scale='normal'`) via a single versioned, backed-up migration step —
  every existing school's sheets render byte-for-byte the same as before until an admin
  deliberately changes one of these.
- `fit_to_page` reuses the established `RESULT_BOOL_SETTINGS` pattern (same list every other
  show/hide switch on that page is driven from), so it's automatically wired into the admin
  form, the settings save/validate logic, and `result_sheet_settings()`'s `rs` dict — no new
  one-off plumbing.
- The auto-shrink math itself (`Math.max(0.28,(max/h)*0.965)`, the 0.28 floor) is byte-for-byte
  unchanged from before this phase; it's now only reached when Fit to Page is on **and** the
  sheet (at the chosen font size) actually overflows, instead of unconditionally.
- Orientation is layered as a `<style>` block that appears after the existing
  `result-sheet.css` link in the document head — later same-specificity CSS wins, so it
  overrides the sheet's portrait default without touching that stylesheet, and without
  affecting the broadsheet's own, separate, hardcoded-landscape `@page` rule.

## Files changed

`db.py` (new `page_orientation` / `fit_to_page` / `font_scale` columns + migration,
`fit_to_page` added to `RESULT_BOOL_SETTINGS`, new `FONT_SCALE_FACTORS` /
`PAGE_ORIENTATIONS` / `FONT_SCALE_CHOICES`), `app.py` (`result_sheet_settings()` now returns
`page_orientation`, `font_scale`, `font_scale_factor`), `v62_routes.py` (admin settings route
validates and saves the two new fields), `templates/result_display_settings.html` (new
controls), `templates/result_print.html` (orientation `@page` override, `fit()` rewritten to
read font_scale/fit_to_page), `templates/broadsheet_print.html` (font_scale applied to its
own width-fit).

Also touched, test-fixture-only (see "A regression this phase caused, and why" below):
`tests/v62_scenarios.py`, `tests/v64_scenarios.py`, `tests/v65_scenarios.py`.

## Database changes

New migration `print_orientation_fit_font_scale_v73` — adds `page_orientation` (TEXT,
default `'portrait'`), `fit_to_page` (INTEGER, default `1`), `font_scale` (TEXT, default
`'normal'`) to `result_display_settings`, via `ensure_column` (safe on a table that already
has rows) following the exact pattern of every prior `result_display_settings` migration in
this project. Runs automatically on next app start, after the usual automatic backup.

## A regression this phase caused, and why it's fixed in the tests, not the feature

Adding `fit_to_page` to `RESULT_BOOL_SETTINGS` means any form submission to the settings page
that doesn't explicitly check that box submits it as **off** (that's how HTML checkboxes
work — this is exactly the same mechanism every other switch on that page already follows).
Three existing test fixtures build settings-page form payloads from their own fixed lists of
"boxes to check" that predate this phase and don't know about the new one:
`tests/v62_scenarios.py`'s `RES_ON` list (also reused, via import-by-copy, in
`v64_scenarios.py` and `v65_scenarios.py`), and a separate `settings()` helper in
`v65_scenarios.py` that only carries over keys starting with `show_` (and `fit_to_page`
doesn't start with `show_`). Both silently turned Fit to Page off on every save, which broke
several "PDF is exactly one page" checks — a real behavioural side effect of adding the
switch, not a defect in the switch itself. Fixed by updating those three fixtures to keep
Fit to Page on (matching its own default), the same "update the old test for an intentional
change" approach used throughout this project; no app/template code was touched for this.

## Tests

New `tests/v73_scenarios.py` / `tests/test_v73_behavior.py` — 30 checks: defaults reproduce
today's exact behaviour (portrait, Fit to Page on, Normal font, byte-identical `@page` rule
and shrink formula); orientation actually flips the rendered `@page` rule and JS flag, while
the broadsheet stays landscape regardless; Fit to Page toggling is reflected in the print
page's JS flag; all three font sizes map to the correct zoom factor on both the result sheet
and the broadsheet; the shrink formula and its overflow-detection are unchanged in shape and
still gated correctly; the admin settings page has the new controls with the right options,
and saving through the real route (not just direct SQL) persists and round-trips correctly.

Full existing suite re-run: v60 (213), v61 (292), v62 (238), v63 (107), v64 (116), v65 (235),
v66 (17), v67 (13), v68 (12), v69 (20), v70 (39), v71 (30), v72 (9) — all still pass, no
regressions. 1,371 checks total across the whole suite, 0 failed.

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
   cp new_version/school/db.py school-results/db.py
   cp new_version/school/app.py school-results/app.py
   cp new_version/school/v62_routes.py school-results/v62_routes.py
   cp new_version/school/templates/result_display_settings.html school-results/templates/
   cp new_version/school/templates/result_print.html school-results/templates/
   cp new_version/school/templates/broadsheet_print.html school-results/templates/
   ```
6. No new dependencies, but the database migration runs automatically next time the app
   starts:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**. The migration runs on this reload (watch the
   error log briefly if you want to confirm — it logs each migration step).
8. Test it: go to **Admin → Result Display Settings**. You should see a new "Page orientation"
   dropdown and "Print / PDF font size" dropdown under Branding & layout, and a new
   "Automatically Shrink to Fit One Page" switch under a new "Page & print" section. Try
   Landscape on a result sheet, try "Large" font size, and try turning Fit to Page off on a
   long result sheet to see it flow onto a second page instead of shrinking.

## Still outstanding (next phases)

Executive Band and Compact Academic template fixes (still need your description of what's
wrong — see V72's notes), mobile/tablet/desktop responsiveness pass, and hiding instructional
text/help/highlights by default (reveal on tap/click).
