# V78 — "Print" now looks exactly like "Download"

This covers what you flagged with the three screenshots on 2026-10-19:

> "Print and download has different interface. Print does not render well or fit to page."

## What was actually happening

Looking at your screenshots: "Download PDF" gave you the correct, fully-styled result sheet
(logo, blue header, colored "Overall Position" badge, everything sized to fit one page — your
second screenshot). "Print" gave you a plain, uncoloured version that spilled onto a second page
(your first and third screenshots).

Both buttons were showing the exact same result sheet, built from the exact same template. The
difference was **who was doing the printing**:

- "Download PDF" is built on our server: we open the result sheet in a headless Chrome instance
  ourselves and tell it, explicitly, to keep all the colors and backgrounds and to shrink the page
  to fit — so it always comes out the same, correct way no matter whose phone opens it.
- "Print" instead handed that same page to **your phone's own print feature** and trusted it to
  print it correctly. That turned out to be the weak link: your phone's print pipeline (Android's
  system Print, via Chrome) doesn't reliably keep background colors or apply the page's "shrink to
  fit one page" logic the way our own server-side rendering does. Different phones/browsers/Android
  versions can behave differently here — it's genuinely outside our control once the page is handed
  off to print on someone else's device.

## The fix

"Print" no longer asks your phone to print the live web page. Instead, tapping "Print" now opens
the **exact same PDF** that "Download PDF" produces — the one you already confirmed looks right —
so you can view and print it from there. There's nothing left that can come out different, because
it's literally the same file.

In practice: tap "Print" and your phone opens that PDF (the same way it already does when you tap
"Download"). From there, use your PDF viewer's own print button (most have one, or it's under
Share) or your phone's print option on the already-correct PDF. One extra tap versus before, but
what gets printed will now always match what you saw on "Download."

This applies to both places that had this same mismatch: a student's individual result sheet, and
the class Broadsheet.

**Files changed:** `app.py` (every "Download PDF" route now also accepts `?inline=1`, which opens
the PDF for viewing instead of saving it straight to Downloads — the Download button itself is
untouched and still saves the file as before), `templates/result_print.html`,
`templates/broadsheet_print.html` (their "Print" buttons now open that same PDF instead of calling
the browser's own print function).

Not touched, on purpose: the Annual/Cumulative Result and Cumulative Broadsheet pages' own "Print"
buttons. Those use a different, much simpler layout (no colored headers or special one-page
shrinking), which browsers already print correctly, so there was nothing to fix there.

## Testing

- `tests/v78_scenarios.py` (+ `tests/test_v78_behavior.py` pytest wrapper) — new: confirms the PDF
  routes still download normally by default and switch to "open to view" with `?inline=1`; confirms
  both print pages' "Print" button no longer calls the browser's print function; and actually clicks
  the Print button in a real headless browser to confirm it requests that exact PDF.
- One existing V61 check had to be updated (it was checking for the literal old `window.print()`
  autoprint code, which intentionally changed) — not a sign of a bug, just an old test asserting the
  old implementation detail.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v78_scenarios.py`): **1,461
  checks, 0 failed.**

## Installing this update on PythonAnywhere

Normal update, no new database columns or tables — just reload after uploading.

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v78.db
   ```
3. Upload the new zip and replace:
   - `app.py`
   - `templates/result_print.html`
   - `templates/broadsheet_print.html`
   - `tests/v78_scenarios.py` (new)
   - `tests/test_v78_behavior.py` (new)
   - `tests/v61_scenarios.py` (one check updated, see Testing above)
4. Go to the **Web** tab and click **Reload**.
5. Open any published student's result on your phone, tap "Print", and confirm it opens the same
   colored, one-page PDF that "Download PDF" gives you.
