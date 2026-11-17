# V108 — adds Theme & Branding backgrounds (spec item 7) and the shared notification banner (spec item 9)
Everything in V107_IMPLEMENTATION_NOTES.md still applies. V108 = V107 + the two items below.

## 7. Theme & Branding backgrounds
* Theme page > **Backgrounds**: Standard / Preset (8: Soft Sky, Fresh Mint, Warm Sand, Lavender Mist, Calm Slate, Ocean, Sunset, Emerald) / Custom colour /
  Custom gradient (two colours + angle). **Live preview** (React) shows a dashboard and a sign-in page, in light or dark, instantly. **Reset to default theme**
  restores colours, sidebar/header style, standard background and switch OFF (logo, name, fonts are kept).
* **Apply Custom Background to Authentication Pages: ON/OFF.** ON: the sign-in, sign-up and other authentication screens of THAT school use the background.
  OFF (default): the standard professional backgrounds. A visitor whose school cannot be identified always gets the standard page (no cross-school leak).
* **Readable on every choice.** `branding_backgrounds.py` builds all CSS from validated values only (preset key, #rrggbb, angle). Text colour is chosen by
  real WCAG contrast and, where the colours alone cannot give 4.5:1, a translucent scrim is added automatically. Tested: all presets and 3,000 random custom
  backgrounds never fall below 4.5:1 in light or dark. Forms, inputs and buttons sit on opaque surfaces, so they stay readable.
* The preview JavaScript is a port of the server builder; a test runs both on 600 random inputs and requires identical output.
* Migration `custom_background_v107` adds `schools.bg_mode / bg_preset / bg_color1 / bg_color2 / bg_angle / bg_apply_auth` (existing schools: standard look, OFF).

## 9. Shared notification banner
* The banner (`_announcement_banners.html`, included once by `base.html`) already existed; it now serves **every** audience: School Admin, Teacher,
  **Accountant, Registrar, other staff** (matched by RBAC role; an Accountant who is not a teacher no longer sees Teacher banners), Student, Parent and the
  **Super Admin** dashboard (new "Super Administrators (platform)" audience, creatable only by the platform owner).
* **Priorities:** Information, Good news, Important, **Urgent** (new). Ordered Urgent > Important > Good news > Information; Urgent banners are announced
  assertively (role=alert). Light and dark styles.
* **Display duration:** administrators set "Auto-hide after N seconds" (0 = stay until dismissed/expired; max 600). The countdown pauses on hover/focus.
  Existing start/expiry dates, dismissal per person and tenant isolation are unchanged. Migration `announcement_duration_v107`.

## Still not delivered
3 (identical print and download: needs an HTML-to-PDF engine), 10 (role-by-role charts incl. an Accountant dashboard), 11 (React for the remaining data-entry
forms). Offline sync does not exist in this build (online-only); PostgreSQL/Neon and Cloudflare R2 are not part of this codebase.

## Tests
`tests/v107_scenarios.py` now has 138 checks (sections 1-9 from V107, 10 = backgrounds, 11 = banners). Full suite result: see the release summary.
