# V99 — Watermark/margin, fit-to-page, cumulative PDF clipping, Days Late, and live preview

Your request, verbatim, with one screenshot (a mobile view of the on-screen result sheet, two
hand-drawn arrows pointing at the watermark area above the school name): *"Adjust the result sheet
to fill in this areas marked on this screenshot, the margin is too much. Allow assigned class
teacher to save result after inputting domain ratings even when principal comments is toggled on.
Cumulative annual performance result sheet does not fit to screen/page on A4 resolve it. Printing
result does not fit to screen/page resolve it. When you click on download only 3rd term result
sheet shows on cumulative annual performance result sheet resolve it. Water mark should be
properly placed on result sheet. Add number of days late to result display settings. On live
preview display cumulative annual performance result when it's toggled on in settings."*

Eight items, below.

## 1 & 6. The margin/watermark problem — one root cause, found and fixed

Your screenshot's arrows were pointing at what looked like empty space above the school name, but
it wasn't empty space at all — it was the watermark. A CSS rule meant to make the watermark "float
behind" the sheet's content (`position:absolute`, so it never takes up real space) was being
silently overridden by a later, equal-priority rule, flipping it back to a normal block element.
A normal block sized to a (sometimes long, rotated) school name takes up real space and pushes
everything below it down — which is exactly what read as "too much margin" at the top of the sheet.

Fixed by excluding the watermark from that later rule, confirmed by directly reading the browser's
own computed style before and after (`position: relative` → `position: absolute`) and by a
side-by-side screenshot: the watermark now floats faintly behind the content instead of shoving the
header down. The watermark text box was also narrowed and given a smaller, tighter line height, so
a long school name wraps compactly instead of sprawling.

## 2, 3 & 4. Fit-to-page, print, and the cumulative PDF showing only one term — one shared bug

These three turned out to be the same underlying bug wearing three different complaints. Chromium
renders every downloaded PDF at a fixed width that happens to equal A4's width (794px) — which is
*narrower* than a breakpoint in the stylesheet meant only for genuine on-screen phone viewing
(`820px`). That breakpoint was never scoped to on-screen viewing only, so it was silently matching
during *every* PDF download, and during native printing on any phone too. Three things it wrongly
switched on there, meant only for a small phone screen:

- The wide Cumulative/Annual Performance table got wrapped in a scrollable box — which, on a static
  PDF page, means whatever's scrolled out of view simply isn't in the PDF. Depending on how that
  scrolled, this is what read as "only the 3rd term shows."
- The ID/Attendance sections collapsed to a cramped 2-column mobile layout instead of the intended
  4-column one, and the whole subject table's font shrank to a smaller mobile size — both making an
  already-fitted sheet look more cramped than it should, even after the fit-to-page shrink ran.
- The sheet's own padding briefly fought the fit script's sizing before the script corrected it.

Fixed by scoping that breakpoint to on-screen viewing (`@media screen`) only, so it never applies
during a PDF download or a native print, on any device — while genuine on-screen mobile viewing
(the only thing it was ever meant for) is completely unchanged. Confirmed directly: under the exact
conditions a PDF is rendered in, the ID grid now computes as the full 4-column layout and the
cumulative table's scroll box now computes as `overflow-x: visible` (not clipped) — both flipped
the other way before the fix.

*A note on fit-to-page: there's one honest limit that didn't change — if a result genuinely has too
much content to stay legible on one page even at the smallest allowed print size, it's still
allowed to flow onto a second page (with an on-screen notice explaining why) rather than ever being
shrunk to illegible text. That's a deliberate legibility floor from V98, not a bug.*

## 5. (covered above, same fix as #1)

## 7. "Days Late" added to Result Display Settings

V97 added a "Days Late" attendance figure to the result sheet, but — unlike Days School
Opened/Present/Absent, which each have their own on/off switch — it always showed, with no toggle.
There's now a "Show Days Late" switch in Result Display Settings → Attendance, defaulting to on (so
nothing changes for a school that doesn't touch this setting). Turning it off removes "Days Late"
from the on-screen sheet, the live preview, Print, and the downloaded PDF (including the
fallback PDF builder used when Chromium isn't available on the host).

## 8. Live preview now shows the Cumulative/Annual state when it's switched on

Previously, the live preview on the Result Display Settings page always showed a per-term result —
even for a school with Cumulative/Annual Results switched on, so there was no way to see what that
state actually looks like without leaving the settings page to check a real student's result.
The preview now builds a realistic two-term sample Cumulative/Annual Performance table (using the
exact same component the real cumulative sheet uses) whenever that setting is on, so toggling it
and saving shows you the cumulative/annual look immediately, right there in the settings page.

## About the class-teacher save issue

I looked closely at "allow the assigned class teacher to save after inputting domain ratings even
when principal comments is toggled on" — read through every save-permission check in the code and
ran a live reproduction (class teacher, domain ratings, principal comment toggle on) and couldn't
find or trigger any rule blocking that save; saves went through cleanly every time. It's possible
this was actually a side effect of the margin/fit bugs above (e.g., the Save button or a field
being pushed out of a usable position by the watermark/layout issue), which are now fixed. If it
still happens after this update, let me know what you see when it fails (an error message, or a
screenshot) and I'll dig further with that in hand.

## Testing

- All 75 existing test suites pass, including one (`v85_scenarios.py`) whose own engineered
  "wide enough to need landscape" fixture needed re-tuning: it had been (unknowingly) relying on
  two of the exact bugs fixed in #1/#2 above to create enough of a size difference between
  portrait and landscape to trigger — with those genuine bugs fixed, the scenario needed a
  slightly different (still realistic) fixture to keep demonstrating the same real behavior
  (auto-orientation genuinely measuring and picking the less-squeezed layout). The check itself,
  and the real behavior it verifies, is unchanged.
- New: a direct computed-style check confirming the on-screen-only breakpoint no longer matches
  under PDF-render or native-print conditions, at any viewport width that would previously have
  triggered it, while still applying correctly for genuine on-screen phone viewing.
- New: an end-to-end check of the Days Late toggle — default-on, hides correctly when switched off
  (both on the print sheet and the PDF fallback builder), and restores correctly when switched back
  on, with the settings-page live preview matching throughout.
- Manually verified: the watermark no longer pushes the header down at any school-name length; a
  genuine 3-term cumulative result's downloaded PDF now contains all three terms' data.
