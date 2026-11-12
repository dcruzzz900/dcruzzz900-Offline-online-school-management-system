# V74 — Hide instructional/help text by default, reveal on tap/click

Tenth phase against the full "Functional and UI/UX Requirements" document: "hiding
instructional text/help/highlights by default, reveal on tap/click."

Executive Band and Compact Academic (the two template fixes from V72's queue) are still
waiting on your description or screenshot of the actual problem — no update there this
round.

## What I found before changing anything

A sitewide audit turned up **139** occurrences of `class="muted"` across **58** template
files. Almost all of them are either:

- short inline labels (ON/OFF badges, "Protected — only admin can change", one-clause
  captions), or
- **status / empty-state messages** — "No scores have been entered for this term yet", "No
  active code. Students cannot complete a first login until you generate one.", "You are not
  assigned as Form/Class Teacher of any class" — which are real page content and feedback,
  not instructional clutter. Hiding those behind a tap wouldn't declutter the page, it would
  hide information the user actually needs to see (and in several cases it's the *entire*
  content of that panel when empty).

Only a genuine subset was actually "how this feature works" explainer prose — multi-clause
paragraphs that explain a mechanism rather than report a state. That subset turned out to be
**8 paragraphs across 3 files**, all in settings/setup pages (the exact kind of page this
requirement is aimed at: an admin who already knows how a toggle works doesn't need a
paragraph of explanation permanently sitting under it, but a first-time user should be able
to tap for it):

- `templates/result_display_settings.html` (6): how "Next Term Resumes" picks a date, how
  Passport/Logo defaults behave, how orientation/font-size/Fit to Page interact, how comment
  suggestions work, how the Cumulative/Annual Result toggle works, and where term resumption
  dates come from.
- `templates/student_account.html` (1): why the official-details fields are locked.
- `templates/timetable_setup_v2.html` (1): how period structure gets applied to every
  ticked school day.

## What changed

Each of those 8 paragraphs is now wrapped in:

```html
<details class="hlp"><summary class="hlp-t">How X works</summary>
  <p class="muted hlp-b">...the original explainer text, unchanged...</p>
</details>
```

`<details>`/`<summary>` is the native HTML collapse mechanism — it already existed in this
codebase in 5 other places (Quick Actions' "View All Actions", Roles & Scope's per-staff
permission panel, Timetable Setup's school-days section, Parent Signup, Student Login's
"Two schools use my number?"), so this reuses an established pattern instead of inventing a
new JS toggle. It needs no JavaScript, is keyboard- and screen-reader-accessible out of the
box, and degrades gracefully (shows the summary line, expandable) if CSS somehow fails to
load.

New CSS (end of `static/css/style.css`) styles the `<summary>` as a small "?" badge next to
a short label, rather than reusing the existing heavier `<summary class="btn ...">`
button look used for the "View All Actions" case — that one is a genuine expand-a-whole-
section control, this is a lighter inline "tap for an explanation" affordance, so it gets its
own lighter treatment. The actual help text keeps its existing `.muted` (de-emphasized grey)
styling once revealed.

## Why this holds — and why most of the 139 occurrences were deliberately left alone

- Short inline labels and one-clause captions were left exactly as they were: wrapping a
  3-word caption in a tap-to-reveal control would add a click for no benefit, which is the
  opposite of decluttering.
- Status and empty-state messages were left exactly as they were, on purpose: these aren't
  instructions about how a feature works, they're the system telling the user what's
  currently true (no code generated yet, no scores entered yet, not assigned to any class).
  Hiding them would be a real usability regression, not a cleanup — so this phase explicitly
  did NOT touch `ai_privacy.html`'s "No AI activity recorded.", `class_login_codes.html`'s
  "not assigned"/"no active code" messages, or `reports_analytics.html`'s "no scores entered"
  message, even though all of them use the same `.muted` class as the paragraphs that WERE
  converted. The test suite (below) explicitly checks that these specific messages are still
  rendered as plain, always-visible text.
- Short signpost sentences that point to where a related setting lives ("Logo and
  header-text alignment... are set in Result Display Settings", "Login & signup branding is
  managed in Theme & Branding") were also left alone — these aid page-to-page discoverability
  rather than explain a mechanism, and burying them behind a tap would make a feature harder
  to find, not easier to read past.
- Nothing about how any setting is saved, validated, computed, or displayed changed — this
  phase only changes whether an explanatory sentence is shown open or closed by default; the
  text itself is byte-for-byte unchanged and still fully present in the page (collapsed, not
  deleted), so anyone who wants it can still get it in one tap.

## Files changed

`static/css/style.css` (new `.hlp`/`.hlp-t`/`.hlp-b` rules), `templates/result_display_settings.html`,
`templates/student_account.html`, `templates/timetable_setup_v2.html`.

## Database changes

None.

## Tests

New `tests/v74_scenarios.py` / `tests/test_v74_behavior.py` — 21 checks: all 8 target help
blocks render as a closed-by-default `<details class="hlp">` with a tappable `<summary
class="hlp-t">` trigger; every target paragraph's original text is still present in the page
(collapsed, not deleted); the per-term resumption-date list and the Timetable Setup Status
summary (both real data, not explanatory prose) are confirmed to sit OUTSIDE any help block
and stay always-visible; and three representative status/empty-state messages elsewhere in
the app (AI Privacy's "No AI activity recorded.", Class Login Codes' "not assigned" message)
are confirmed to remain plain, un-hidden text, proving the scope decision above was actually
followed and not just described.

Full existing suite re-run: v60 (213), v61 (292), v62 (238), v63 (107), v64 (116), v65 (235),
v66 (17), v67 (13), v68 (12), v69 (20), v70 (39), v71 (30), v72 (9), v73 (30) — all still
pass, no regressions. 1,392 checks total across the whole suite, 0 failed.

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
   cp new_version/school/static/css/style.css school-results/static/css/style.css
   cp new_version/school/templates/result_display_settings.html school-results/templates/
   cp new_version/school/templates/student_account.html school-results/templates/
   cp new_version/school/templates/timetable_setup_v2.html school-results/templates/
   ```
6. No new dependencies and no database migration this time:
   ```
   workon schoolenv
   cd school-results
   pip install -r requirements.txt
   ```
7. Go to the **Web** tab and click **Reload**.
8. Test it: open **Admin → Result Display Settings** — you should see small "?" links (e.g.
   "How 'Next Term Resumes' works") that expand an explanation when tapped, instead of a
   permanent paragraph. Check a student's **My Account** page and **Timetable Setup** the
   same way. Confirm pages with "No scores yet" / "not assigned" style messages look
   unchanged — those were deliberately left alone.

## Still outstanding (next phases)

Executive Band and Compact Academic template fixes (still need your description of what's
wrong — see V72's notes), and the mobile/tablet/desktop responsiveness pass.
