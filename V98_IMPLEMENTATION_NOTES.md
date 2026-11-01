# V98 — Default result design, cumulative summary, cumulative fit-to-page, and Print no longer downloads

Your request, verbatim, with two screenshots (one a correct preview of the current design, one a
downloaded PDF showing an old, wrong design): *"Use the 1st photo interface as default result,
remove the 2nd photo from my school result management system. Academic Performance Summary should
show on cumulative/annual performance result sheet. Let cumulative/annual performance result sheet
fit to page. Print should not automatically download page."*

Four fixes, below.

## 1. The old design in your second screenshot — found and removed

Your second screenshot was a **downloaded PDF** ("result_003_1st_Term (3).pdf") showing an old
design: "Overall Position: 1st of 3" instead of "Class Position: 1/3", "Grading key:" instead of
"Grading Scale:", and no Avg. column — none of which match the current design (your first
screenshot) at all.

The cause: this system builds every result PDF with a real browser engine (Chromium) so the PDF is
pixel-for-pixel the same as what you see on screen — but if Chromium isn't available on the server
for any reason, it silently falls back to a second, much older, hand-coded PDF builder
(`pdf_utils.py`) that was never updated past an early design from before Cumulative/Annual Results,
the Avg. column, or the current wording existed. That fallback is exactly what your second
screenshot shows, and it's a known limitation your system has flagged before (an admin-only warning
about it was added back in V87) — PythonAnywhere-style hosting commonly can't run a full browser
engine, so this fallback can end up doing most or all of the real work there without it being
obvious from the result sheet itself.

Rather than leave that fallback stale and hope it's rarely used, **it's been rewritten to match
your current, single design exactly**: "Class Position: pos/size" (not "Overall Position"), the
Avg. column and TOTAL/AVERAGE footer rows on the subjects table, the new Academic Performance
Summary strip, and "Grading Scale:" wording. The old 16-style switching code inside it (left over
from before results were unified to one design) is gone too. So even on a host where the
Chromium-based path can't run, downloaded PDFs now show the same design as everything else —
there's no second design left anywhere in the system for "the 2nd photo" to have come from.

Verified directly: with the Chromium path turned off (simulating exactly the condition that
produces this fallback), a real downloaded result PDF was generated and checked — it contains
"Class Position", "Academic Performance Summary" and the Avg. column, and no longer contains
"Overall Position" or "Grading key".

*If PDFs are still slow, time out, or you want to confirm which path is actually serving your
PDFs on your host, that's a separate, worthwhile thing to check — the admin dashboard already
shows a warning banner when the Chromium path is unavailable (since V87); if you ever see that
banner, it means downloads are coming from this fallback.*

## 2. Academic Performance Summary now shows on the cumulative/annual sheet too

Previously this 6-up strip (Total Subjects / Total Score / Average Score / Percentage / Grade /
Remark) only appeared on the per-term result. It's now shown on the Cumulative/Annual state too,
using the same Average/Grade/Remark your Annual/Cumulative Result page and class broadsheets
already use — so the Grade shown here always agrees with the Grade shown everywhere else for that
student's cumulative result, rather than introducing a second, differently-calculated figure.

## 3. Cumulative/Annual Performance sheet now fits to page

The Cumulative/Annual Performance table grows wider with every extra term in the session (each
term repeats its own CA1/CA2/CA3/Exam/Total/Avg./Pos. columns), so a result with several terms
needs more horizontal room than a plain per-term sheet does. The result sheet now automatically
picks whichever page orientation — portrait or landscape — needs the least shrinking to stay
legible on one page, specifically when it's showing cumulative data, regardless of the school's
general saved Page orientation setting (which still applies normally to plain per-term sheets).

One honest limit: if a session has enough terms that even landscape can't fit the table onto one
page at a readable size, the sheet still won't force text down to an illegible size — it shrinks as
far as it reasonably can and then lets the result flow onto a second page, with an on-screen notice
explaining why, rather than ever producing unreadable text. Auto-orientation fixes the common case;
it doesn't change that one deliberate legibility floor.

## 4. Print no longer downloads a file

"Print" previously opened the exact same PDF file "Download PDF" produces (this was a deliberate
earlier fix, V78, for a different complaint — that a phone's own print pipeline didn't reproduce
colors or the one-page fit correctly). On your device, though, that approach was itself producing
exactly the broken experience you just reported: tapping "Print" immediately forced a PDF into your
phone's Downloads instead of showing you anything to view or print — a known behavior on many
phones and installed/PWA browsing contexts, which don't render a downloaded PDF inline regardless of
how the server marks it.

"Print" now calls the browser's own native print dialog directly, the way a "Print" button normally
works, instead of fetching a PDF at all. The page's existing one-page auto-shrink already re-runs
right before printing, and the stylesheet already forces exact color reproduction in print — both
pieces V78 was worried a phone's print pipeline wouldn't handle correctly — so this should avoid
re-introducing that original problem while fixing the download issue you just hit. "Download PDF"
is unchanged and still gives you an actual PDF file whenever you want one. Applies to the individual
result sheet, the cumulative/annual sheet, and the broadsheet — every page with a Print button.

*If Print still doesn't look right on your specific phone/browser after this (colors missing, or
not fitting one page), that would point back to that device's own print pipeline rather than
something in the system — worth a quick check once you've had a chance to try it.*

## Testing

- All 37 existing test suites (v60–v96) pass, including two whose assertions needed updating for
  this phase's intentional behavior changes, not newly broken ones:
  - `v61_scenarios.py` — a literal reference to the old `printPdf()` function name, renamed to
    `doPrint()`.
  - `v78_scenarios.py` — this file documented and tested the V78 "Print = Download" design head-on;
    it now documents and tests the V98 reversion instead (Print uses `window.print()`, confirmed by
    a real headless-browser click that no PDF request fires), while keeping its still-valid checks
    that the PDF routes themselves (`?inline=1` vs. plain) are unaffected.
  - `v85_scenarios.py` — a quoting-style mismatch in a new check (now fixed, no behavior change).
- New: a standalone check that forces the Chromium path off and fetches a real result PDF through
  the rewritten `pdf_utils.py` fallback, confirming it returns a valid PDF containing "Class
  Position", "Academic Performance Summary" and an Avg. column, and no longer "Overall Position" or
  "Grading key" — i.e., confirming your second screenshot's design is gone for good, not just
  less likely to appear.
- Manually verified: the cumulative-state per-term print page shows both the Cumulative/Annual
  Performance table and the new Academic Performance Summary together, and auto-picks its page
  orientation, with real multi-term data.
