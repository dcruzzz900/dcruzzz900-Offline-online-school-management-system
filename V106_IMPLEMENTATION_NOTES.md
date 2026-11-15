# V106 — Gender on result sheet, shared Gender Distribution, Light/Dark mode

This is phase 1 of the round you asked for (gender, theming/branding, Bootstrap, React filtering,
React live preview, React score entry, dark mode). As agreed, it's delivered in phases like every
other round — this phase covers the lower-risk, immediately-useful pieces; the React/Bootstrap
work is phase 2 and 3, coming next.

## What's in this round

### 1. Gender on the result sheet
- New toggle in **Setup → Result Display Settings → Student details → "Show Student Gender"**,
  ON by default. Shows "Male"/"Female" right under the student's name.
- Added to every place a result is produced, not just the on-screen view, so they can never
  disagree: the regular per-term result sheet, the Cumulative/Annual sheet, the live preview on
  the settings page, the Chromium PDF pipeline, and the older reportlab fallback PDF builder
  (used only on a host without `playwright install chromium` — V87/V98 already flagged that
  gap, this keeps it in sync too).
- Broadsheet (whole-class grid) was deliberately left alone — it already has a dedicated column
  layout tuned to fit one page, and gender per-student there wasn't part of what you asked for.

### 2. Gender Distribution now shared/inherited everywhere it appears
Before this round there were three different gender-distribution widgets: the new donut on the
Admin Dashboard (V105), an older Chart.js donut on **School Analytics**, and a third Chart.js
donut on the **Teacher Dashboard**. Now there's one: `templates/partials/gender_donut.html`'s
`gender_donut()` macro (the exact donut + legend the V105 admin dashboard introduced), used by
all three. School Analytics and Teacher Dashboard no longer load a separate Chart.js canvas for
this — same look, same colours, same markup everywhere. The shared CSS lives in
`static/css/gender-donut.css` (admin-dashboard.css now `@import`s it instead of keeping its own
copy, so there's one source of truth, not two that could drift apart).

### 3. Light / Dark mode
A toggle button (sun/moon icon) is now in the top bar on every screen. Click it to switch; it's
remembered per-browser (localStorage) and respects your device's OS setting the first time, with
no flash of the wrong theme on page load.

Scope: this covers the shared app shell every screen is built from — sidebar, top bar, cards,
tables, forms, buttons, chips, the sign-in/registration pages, and the Result Display Settings
page. It does **not** touch the result sheet, broadsheet or any printed/PDF output — those stay
exactly as themed by your own school branding colours regardless of which mode you're browsing
in, which is deliberate: what prints should never depend on the browsing mode of whoever clicked
Download. Your brand colours (sidebar gradient, buttons, KPI card colours) are unchanged in both
modes — dark mode only changes the neutral chrome (backgrounds, borders, body text), not your
branding.

**Known gap, flagged not fully solved:** this app has ~20 separate, overlapping CSS files built
up over many rounds (the "v46/v47 duplication" flagged back in V87's notes and still out of
scope to fully clean up). Dark mode overrides the shared shell broadly and I verified it on the
admin, teacher, score entry, settings and sign-in screens — but a handful of less-common screens
with their own one-off hardcoded colours may still show a light element here and there. If you
spot one, send a screenshot and I'll patch that specific spot rather than trying to re-guess the
whole stylesheet stack.

### "All screens should respond to theme and branding"
Covered via the dark mode work above for the *theme* half (light/dark). *Branding* (your accent
colour, logo, school name) already flows through `--theme-primary`/`--theme-secondary`/
`--theme-accent` CSS variables sitewide since earlier rounds (V46/47-era) — this round didn't
change that, just made sure dark mode doesn't fight with it (brand colours stay as you set them
in both modes).

## Testing
Full regression: all 43 suites (`tests/v60_scenarios.py` through `tests/v105_scenarios.py`), 0
failures. Two suites (`v95`, `v96`) had assertions tied to the *old* separate Teacher/Analytics
gender chart implementation — updated to check for the new shared component instead of weakening
them (same "fix the stale assumption, don't weaken the check" precedent as earlier rounds).
Verified visually (Playwright screenshots, light + dark) on: Admin Dashboard, Teacher Dashboard,
School Analytics, Result Display Settings (incl. live preview), Score Entry, and the sign-in page.

## Up next (phase 2 / V107, as discussed)
- React (via CDN, no build step) managing the dashboard term/class filter controls so Chart.js
  charts refresh without a page reload.
- React-driven score entry: live CA1/CA2/CA3/Exam totals and grades as a teacher types, instant
  max-score validation, per-row save status.

## Then (phase 3 / V108)
- React-driven instant live preview on Result Display Settings (every toggle updates the preview
  immediately, not just on Save).
- Bootstrap added to the screens touched in this round (dashboards, settings, score entry) for
  new components going forward — result-sheet/print templates stay exactly as they are.
