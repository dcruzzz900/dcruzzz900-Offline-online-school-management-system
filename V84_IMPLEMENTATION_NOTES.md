# V84 — Final Security & Regression Pass (Phase 7 — the last phase)

This closes out Phase 7 of your "Consolidated Development Specification" document —
**"Security/Regression Testing and Deployment"** — the final phase of the whole 7-phase roadmap.
With this round delivered, **all seven phases of that document are complete.**

## What this round was

Rather than one feature, this was a deliberate audit of the whole application's security posture
and a full regression confirmation, done the same careful way as every other round: look closely,
fix anything real that turns up, test it properly, and write it up honestly.

## What I checked, and confirmed is already solid

- **CSRF protection** is enforced globally on every state-changing request (not opt-in per page) —
  confirmed a submission with no token, or a forged one, is rejected either way.
- **Brute-force protection** on sign-in and every other sensitive public form (registration,
  activation, account recovery) is in place and genuinely engages after repeated attempts.
- **Security response headers** (clickjacking protection, MIME-sniffing protection, a strict
  referrer policy, camera/microphone/location locked down by default, HTTPS enforcement on a real
  deployment) are present on every response.
- **No SQL injection paths** — every place the code builds a query dynamically, what varies is a
  placeholder count or a fixed internal field name, never raw user input dropped into SQL text.
- **File uploads** are size-limited, and anything claiming to be an image is verified server-side,
  not trusted by filename alone.
- **Passwords are never stored anywhere in plain text** — checked across every account type (staff,
  students, parents, platform administrators).
- **Tenant isolation** holds on this document's own newest features — a school cannot reach another
  school's cumulative results or branding settings by guessing an id.
- An anonymous visitor is always redirected to sign in, never shown a staff page directly.

## The one real gap found and fixed

Signing in as staff or a parent worked slightly differently, timing-wise, depending on whether the
username/email/phone typed in even existed as an account: a **real account with the wrong password**
always took a small, deliberate moment to check (by design — that's what keeps password-guessing
slow), but an **account that doesn't exist at all** was rejected almost instantly, with no such check
happening. That tiny, measurable timing difference could, in principle, let someone automate probing
your sign-in page to work out which usernames, emails, or phone numbers have real accounts at your
school — without ever triggering a single "wrong password" attempt.

This is now fixed: an unrecognized sign-in now takes the same small, deliberate moment as a real
account with a wrong password, so there's no longer a timing difference to measure. (Student sign-in
already had exactly this protection, built a while back — this just brings staff and parent sign-in
up to the same standard.) There is no evidence this was ever exploited against your school; it's a
hardening fix, not a response to an incident.

## Testing

- `tests/v84_scenarios.py` (+ `tests/test_v84_behavior.py` pytest wrapper) — new, 20 checks covering
  everything audited above: the timing fix is verified to actually engage; CSRF rejection of a
  missing or forged token; all four security headers present; the rate limiter genuinely blocking
  after repeated attempts (the first test in the whole suite that deliberately lets it run rather
  than clearing it); anonymous access redirected away from staff pages; cross-school isolation on
  the cumulative-results and branding pages; and no plain-text passwords anywhere.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v84_scenarios.py`): **1,579
  checks, 0 failed.** This is the complete, cumulative test history of this project across every
  phase of every requirements document to date.

## Installing this update on PythonAnywhere

Small, low-risk update — a few lines in one function, nothing structural.

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v84.db
   ```
3. Upload the new zip and replace:
   - `app.py`
   - `tests/v84_scenarios.py` (new)
   - `tests/test_v84_behavior.py` (new)
4. Go to the **Web** tab and click **Reload**.
5. Nothing to configure or re-test on your end — sign-in behaves identically either way; this only
   changes what happens invisibly, in milliseconds, behind an unsuccessful attempt.

## A deployment reminder (not new, just worth restating now that all 7 phases are done)

Two environment settings matter for a production deployment and are already documented in
`DEPLOY_RAILWAY.md`/`PILOT_CHECKLIST.md`: set `SESSION_COOKIE_SECURE=1` (or `FLASK_ENV=production`)
on any host serving real traffic over HTTPS, and make sure `SECRET_KEY` is set to a stable value
(not auto-generated per restart) if you ever run more than one web worker. If you're only running on
PythonAnywhere and Railway as today, these are very likely already set from earlier rounds — this is
just a reminder to double-check them on whichever host serves your real school data.

## Where this leaves the 9th requirements document

All seven phases are now complete:

1. Centralized Result Configuration ✅ (already in place before this document)
2. One-Page Result Rendering ✅ (V79)
3. Cumulative/Annual Results ✅ (V80)
4. Unified Login and Automatic School Identification ✅ (V81)
5. Username and Password Recovery ✅ (V82)
6. Dynamic Login Branding ✅ (V83, confirmed + one gap closed)
7. Security/Regression Testing and Deployment ✅ (V84, this round)

Nothing further is queued from this document. A short list of smaller, optional follow-ups flagged
along the way (never requested outright) remains noted for whenever you'd like to take them up:
parent/student-facing cumulative results, full Result Display Settings customization on the
cumulative pages, and automatic portrait/landscape switching for one-page printing.
