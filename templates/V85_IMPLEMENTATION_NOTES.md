# V85 — Cumulative Results for Parents/Students, Full Theming on the Cumulative Page, and True Automatic Page Orientation

This round continues the three smaller, optional follow-ups noted (never requested outright) when
the ninth requirements document closed out at V84:

1. **Parents and students can now view their own cumulative/annual result**, the same way they
   already could view a single term's result.
2. **The cumulative result page now takes on the school's full Result Display Settings** — accent
   colors, logo, watermark, footer — the same branding already applied to the regular per-term
   result.
3. **A genuine "automatic" page orientation option**, which measures each specific result and
   picks whichever of portrait or landscape lets it fit on one printed page more legibly — not a
   guess, an actual measurement done by the browser itself.

## 1) Cumulative results for parents and students

Previously, only staff could look up a student's cumulative/annual result (through the class
broadsheet or a direct staff page). Now, from their own "My Result" page, a student sees a "View
cumulative result" link, and a parent sees the same on their child's result page. Both lead to a
simplified version of the same cumulative result staff already see — same figures, same per-term
breakdown, downloadable and printable the same way.

**A deliberate safety rule that's stricter than the staff view:** a parent or student can only see
a cumulative result once the specific term it's cut off at has been published. Staff can look at
an in-progress cumulative figure internally (useful while finishing up a term), but a family member
never sees a number that hasn't been officially released yet — even if an earlier term in the same
session was already published. This mirrors the same publish-gate already protecting the regular
per-term result.

## 2) Full branding on the cumulative page

The cumulative/annual result page, its print view, and its PDF now pick up everything in **Result
Display Settings**: your school's accent and secondary colors, logo, watermark text, and footer
text — exactly like the regular per-term result already did. Previously the cumulative page had a
plain, unbranded look.

The class-wide **cumulative broadsheet** also now shows your accent color and footer text. Its PDF
deliberately stays on the simpler, older builder for now (same scope decision made for broadsheets
generally) — a smaller, lower-priority piece than the single-student cumulative result, which now
goes through the same "what you see is exactly what prints" pipeline the per-term result uses.

## 3) True automatic page orientation

**Result Display Settings → Page orientation** now offers a third choice: **Automatic**. Where
Portrait/Landscape apply to every result sheet regardless of its content, Automatic looks at the
specific result being printed and asks: "does this fit more legibly as a tall page or a wide
page?" — then uses whichever one actually does, for that one result. This applies to both the
regular per-term result and (new, from this round) the cumulative result.

This was deliberately put off twice before (first when one-page printing was built, then again
when cumulative results were added) specifically because doing it honestly — a real measurement,
not a rule of thumb — takes real engineering, and a cut corner here would have meant results
occasionally printing onto an unnecessary second page or shrinking smaller than they needed to.

### Two real, pre-existing bugs found and fixed along the way

Building Automatic required actually testing Landscape under a magnifying glass for the first
time — and in doing so, two genuine bugs turned up in the **already-shipped** Landscape setting
(from the one-page printing round). Both are now fixed, which means **Landscape prints better now
than it did before this round**, for anyone already using it:

- **Landscape wasn't actually using the extra width.** It correctly made the printed *page* wider,
  but the *content* on it was still being held to the narrower, portrait-sized layout underneath —
  so landscape mode mostly just added blank space around the same narrow content, instead of
  genuinely laying it out wider. Now landscape content really does spread across the full wider
  page.
- **Landscape could be shrunk more than it needed to be.** A leftover assumption (sized for a tall,
  portrait page) was being applied even in landscape mode, which could make the "shrink to fit one
  page" feature think a result needed more shrinking than it actually did. Now the shrink
  calculation correctly reflects landscape's own, shorter page height.

Neither of these ever caused incorrect data or printed the wrong information — only unnecessary
blank space and slightly smaller-than-needed text in Landscape mode specifically. If your school
has been using the plain "Landscape" setting already, it will look a little better after this
update with no action needed from you.

### What a typical result does under "Automatic"

An ordinary, single-term result — or a cumulative result with a modest number of terms and
subjects — stays portrait, exactly as before. Automatic only switches to landscape when a result
is genuinely wide (lots of terms, lots of subjects with long names, that kind of thing) and would
legitimately fit better that way — which in practice is mostly going to be the cumulative/annual
view for a student with a long academic history, not the regular single-term result.

## Testing

- `tests/v85_scenarios.py` (+ `tests/test_v85_behavior.py` pytest wrapper) — new, 28 checks: the
  publish-gate on parent/student cumulative access (including that an earlier published term
  doesn't leak a not-yet-published cutoff term), PDF downloads for both, cross-student isolation,
  denial for an unverified parent, the new "View cumulative result" links; full Result Display
  Settings theming on the staff cumulative page, its new print view, its PDF, and the cumulative
  broadsheet; the Automatic orientation choice surviving the save/load round trip without being
  silently reset to Portrait (the exact bug class this round's own whitelist fix prevents); and a
  genuine, end-to-end dual-orientation measurement — verified through the real download route and
  by reading the actual PDF's page dimensions — showing an ordinary result staying portrait while a
  deliberately wide cumulative result (many terms, long subject names, under this school's own
  branding/watermark/footer settings) is measured and switched to landscape.
- Two small, unrelated test-script fixes made along the way, to keep two older regression scripts
  correctly checking today's actual page markup rather than quietly matching nothing: one test's
  pattern for finding the result table was too strict about the table's styling attributes, and one
  explanatory code comment (added by this round) accidentally confused a different test's simple
  text-stripping check. Neither reflects any change in what your school's pages actually look like
  or do — both are fixed and re-confirmed passing.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v85_scenarios.py`): **1,607
  checks, 0 failed.**

## Installing this update on PythonAnywhere

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v85.db
   ```
3. Upload the new zip and replace these files:
   - `app.py`
   - `templates/result_print.html` (Landscape fixes + Automatic)
   - `templates/cumulative_result_print.html` (new)
   - `templates/_cumulative_sheet.html` (new)
   - `templates/cumulative_result.html`
   - `templates/cumulative_broadsheet.html`
   - `templates/student_cumulative_result.html` (new)
   - `templates/parent_cumulative_result.html` (new)
   - `templates/student_result.html`
   - `templates/parent_result.html`
   - `tests/v85_scenarios.py` (new)
   - `tests/test_v85_behavior.py` (new)
   - `tests/v65_scenarios.py`, `tests/v80_scenarios.py` (the two small test-script fixes mentioned
     above — safe to skip if you don't run the test suite yourself, but included for completeness)
4. Go to the **Web** tab and click **Reload**.
5. Nothing needs reconfiguring. To try the new options: open **Result Display Settings** and set
   **Page orientation** to **Automatic**; open any student's result and use the new "View
   cumulative result" link from a student or parent login to see the new self-service page.

## Where this leaves things

With this round delivered, all three of the smaller follow-ups noted after the ninth requirements
document closed out at V84 are now complete. Nothing further is currently queued.
