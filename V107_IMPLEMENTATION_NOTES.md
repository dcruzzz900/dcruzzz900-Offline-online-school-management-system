# V107 — foundation slice of the UI/UX, design and functionality specification

This release delivers part of the specification (see "Delivered" and "Not delivered"). Nothing was removed; existing records, authentication,
roles and tenant isolation are unchanged.

## Delivered
**1. Typography + global text size.** Every `font-size` in the app stylesheets and template styles is now in `rem` (`tools/px_to_rem.py`,
idempotent; result-sheet and print/PDF templates untouched). One root size drives everything: 16px (mobile) / 17px (>=992px) / 18px (>=1400px),
multiplied by the person's A- / A+ choice (90, 100, 115, 130, 150 %). The sidebar width is in rem and goes off-canvas (hamburger) at 130/150 % on
mid-size screens; stat tiles wrap instead of squeezing. Printing is always 16px-based. Saved per person on the server (`ui_preferences`) and mirrored on
the device; works signed-out via the device copy.
**2. Light + dark.** Dark palette exactly as specified (#0B1120 / #111827 / #182235 / #202D40 / #F1F5F9 / #B0BDCE / #334155 / #38BDF8 / #34D399 / #FBBF24 / #F87171);
every text pair passes WCAG AA (tested). Forms, tables, dropdowns, modals, buttons, alerts, focus/hover/active/disabled states styled. Theme is saved per
person on the server and applied before first paint (no flash). `tools/build_dark_css.py` regenerates dark rules for literal colours in the older CSS.
**4/5. Compulsory Date of Birth + Gender.** One rule (`identity_rules.py`) shared by every path: student add / edit / class-roster add / registrar admission /
both CSV importers (columns now required), staff add / staff self-sign-up / staff profile, parent self-sign-up. Server-rendered fields (`partials/identity_fields.html`)
are upgraded by React (`identity-fields.js`): live messages, submit guard, double-submit prevention. Gender is stored `M`/`F`; dates as ISO and accepted as
YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY. New migration adds `parent_accounts.date_of_birth/gender`.
**Existing records:** `/admin/data-completion` (School Admin) lists this school's students, staff and parents still missing either value, with a validated inline
fix. Nothing is ever filled in automatically. A dashboard tile shows how many records need attention.
**6. Passport photographs.** `passport_fit.py` normalises every upload (student, staff, parent, student self-service) to one 600x750 (4:5) JPEG: EXIF-upright,
transparency flattened, never stretched; near-4:5 photos are filled and trimmed slightly from the bottom (faces kept), other shapes are shown WHOLE on a soft backdrop.
Frames use one rule (`.passport-img`). Upload preview (`passport-preview.js`) mirrors the server's rule. Older photos are shown whole (contain).
**8. Shared welcome header.** One React component `DashboardWelcomeHeader` (+ server-rendered fallback macro `partials/welcome_header.html`) on Teacher, Registrar,
Student, Parent and Super Admin dashboards (the Teacher dashboard shows the Accountant / Registrar / other-staff copy by the person's RBAC role). Heading and description are
role-driven; the clock uses the SCHOOL's timezone, 12-hour AM/PM, ticks without refresh, anchored to server time. The School Admin dashboard keeps its original banner.

## Not delivered (needs decisions or a larger piece of work)
* **3. Identical print and download.** The HTML sheet and the PDF are produced by two different renderers (`_result_sheet.html` vs `pdf_sheet.py`/ReportLab). Making them
  identical means rendering the PDF from the HTML (needs a headless-browser / HTML-to-PDF engine on the server) — an architectural change, not done here.
* **7. Theme & Branding backgrounds** (presets, gradients, custom background, authentication-page toggle, live preview, reset).
* **9. Shared notification banner**, **10. role-by-role charts** (Accountant, Registrar, Student/Parent chart sets, Super Admin analytics), **11. React for all data-entry forms**
  (V106 did result entry, result-display settings and dashboard filters; V107 added the identity fields. Fees, attendance, timetable, admissions, assignments, promotion,
  approval, materials, school settings, profiles are still server forms with server validation).
* **Offline / online synchronization:** this build is online-only (the offline mode was retired in an earlier version: see `static/js/online-only.js`). There is nothing to preserve.
* **Architecture in the specification vs this code:** the specification mentions PostgreSQL/Neon and Cloudflare R2; this build uses SQLite with files on disk. Not changed.

## Tests
`tests/v107_scenarios.py` (101 checks). Existing tests updated only where seed data now needs a Date of Birth / Gender (v60, v62, v90, v104) or asserted the
old pixel font size (v62: 16px -> 1rem). See the release summary for the full-suite result.
