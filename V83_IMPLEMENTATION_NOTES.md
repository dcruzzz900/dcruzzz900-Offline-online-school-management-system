# V83 — Dynamic Login Branding: Confirmed, Plus One Gap Closed

This is Phase 6 of your "Consolidated Development Specification" document: **"Dynamic Login
Branding."**

## The headline: this was already mostly built

Unlike the other phases, this one didn't need new functionality — your sign-in page has, for a
while now, automatically shown each school's own name and logo when visitors arrive through that
school's own web address (subdomain), with no "which school are you?" selector anywhere. This round
was a **confirmation pass**: proving that end-to-end, in real tests, for the first time — and it
checks out. Specifically, confirmed working exactly as intended:

- A school's own subdomain (e.g. `greenwood.yourdomain.com`) automatically shows that school's name
  and logo on the sign-in page — no setup needed beyond choosing the subdomain and uploading a logo.
- Two different schools' subdomains never bleed into each other.
- An unrecognized or mistyped subdomain shows the plain, generic page — never an error.
- Reserved addresses (`www`, `app`, `api`, etc.) never accidentally pick up a school's branding.
- A school can turn branding off entirely, even with a working subdomain and logo — the sign-in
  page then shows the generic look, not partial branding.
- A school that isn't active yet (pending, suspended, archived) never shows its branding, even on
  its own subdomain — so no one can see a defunct or not-yet-approved school's logo.

## The one real gap found and fixed

Visiting a school by its own web address was always working correctly. But if someone visited the
**plain, un-branded address** and typed their own login details — and specifically if that was a
**student or parent**, and they mistyped their password — the page would re-show itself in the
generic, unbranded look instead of recognizing their school from what they'd just typed. (Staff
logins already worked correctly here; this gap only affected students and parents, and only
appeared when they weren't already on their school's own subdomain.)

This is now fixed — a failed attempt by a student (admission number, register number, or username)
or a parent (username) now still shows their own school's branding on the retry, the same way it
already worked for staff.

## Testing

- `tests/v83_scenarios.py` (+ `tests/test_v83_behavior.py` pytest wrapper) — new, 20 checks:
  subdomain-based branding for two separate schools, isolated correctly from each other; unknown
  and reserved subdomains fall back to the generic page; the branding on/off switch and the
  active/inactive school check both work even when the subdomain itself resolves correctly; the
  `/auth/branding` status endpoint mirrors the page exactly; a subdomain is trusted over a
  submitted username when both are present; and the fixed gap — a student's or parent's own
  identifier now correctly resolves their school's branding on a failed attempt, the same as staff.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v83_scenarios.py`): **1,559
  checks, 0 failed.**

## Installing this update on PythonAnywhere

Small, low-risk update — one function in `app.py` made a little more thorough, nothing structural.

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v83.db
   ```
3. Upload the new zip and replace:
   - `app.py`
   - `tests/v83_scenarios.py` (new)
   - `tests/test_v83_behavior.py` (new)
4. Go to the **Web** tab and click **Reload**.
5. Nothing to configure — if you already have a subdomain and logo set up for your school (Setup →
   Theme & Branding), it keeps working exactly as before, just a bit more consistently for students
   and parents who mistype their password on the plain/unbranded address.

## What's next

Phase 7 — your spec document's final phase — is a **security/regression testing and deployment
pass**. All seven phases of this document will then be complete. I can run through that whenever
you're ready; it's mostly confirming what's already been tested throughout V79-V83 holds together,
plus a final look at anything that's accumulated since the document was written.
