# V82 — Forgot Your Username or Password? Recover by Email

This is Phase 5 of your "Consolidated Development Specification" document: **"Secure Account
Recovery"** — email-based username/password recovery.

## The problem

The only account-recovery option in the app asked for a **username**, then a **security
question** — and only staff accounts (administrators, teachers) even have a security question set
up. If a parent forgot their password, or a staff member forgot their username, there was no
self-service way to recover — they had to ask you directly every time.

## The fix

There's now a **"Forgot your username or password?"** link on the sign-in page that works by
**email address** instead — for both staff and parent accounts.

1. You enter the email address on your account.
2. If it matches an account, you get an email with your username and a secure link to set a new
   password. The link works once, and expires after 30 minutes.
3. If it doesn't match anything, the page says the exact same thing either way — "if an account is
   associated with that email, we've sent instructions." This is deliberate: it means the page
   can't be used to go fishing for which email addresses have accounts at your school.

**If a parent has the same email address linked to accounts at more than one school** (a
grandparent with two grandchildren at different schools using the same email, for example), they
get a **separate email for each school**, each clearly labeled and each with its own link — never
one confusing combined message, and resetting one never touches the other.

**The old username + security-question recovery page still works exactly as before** — it just
isn't the link shown on the sign-in page any more. A staff member who has no email on file, or who
prefers it, can still use it.

## What was deliberately left out

**Students do not get a self-service recovery option through this.** A student's record only has a
*parent's* email, not their own, and that email is shared with — sometimes shared with — a sibling's
record too. Routing a student's own password reset through a parent's inbox would hand control of
the student's account to someone else, and isn't something your spec asked for. Student passwords
stay staff-assisted, exactly as today: **Setup → Students → Reset Login** (or the class login code
for a brand-new account), which already existed and is unchanged.

## Setting this up

This feature sends real emails, so it only works for a school once **Setup → Email Settings** (the
same SMTP settings already used for emailing results to parents) is filled in. If a matching
account's school hasn't set that up yet, the visitor still sees the same generic "check your email"
message — nothing breaks or errors out, the email is just quietly not sent, the same as if you tried
to email a result today without SMTP configured.

## Testing

- `tests/v82_scenarios.py` (+ `tests/test_v82_behavior.py` pytest wrapper) — new, 29 checks: a
  staff member recovers successfully by email (gets their username and a working link); the link
  works once and is refused if revisited after use; requesting a new link invalidates the one
  before it; an unmatched email and a matched email show the exact same on-screen message (no way
  to tell them apart); a staff account with no email on file can't be reached this way at all; a
  parent with the same email at two different schools gets two separate, correctly-scoped emails
  rather than one mixed-up one, and resetting one never touches the other; a bogus/garbage link is
  rejected cleanly; the old username+security-question page is still fully reachable.
- `tests/v65_scenarios.py` (existing, 1 check updated): the "forgot password" link check now looks
  for the new `/account-recovery` address instead of the old `/recover` one, since that's what the
  sign-in page now links to — not a bug, the test catching up to the new link.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v82_scenarios.py`): **1,539
  checks, 0 failed.**

## Installing this update on PythonAnywhere

This update adds one new, small database table (for tracking one-time reset links) — your existing
data is completely unaffected.

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v82.db
   ```
3. Upload the new zip and replace:
   - `app.py`
   - `db.py`
   - `templates/login.html`
   - `templates/account_recovery.html` (new)
   - `templates/account_recovery_reset.html` (new)
   - `tests/v65_scenarios.py` (one check updated, see Testing above)
   - `tests/v82_scenarios.py` (new)
   - `tests/test_v82_behavior.py` (new)
4. Go to the **Web** tab and click **Reload** — the new table is created automatically the next
   time the app starts, the same as every other update.
5. Try it: make sure **Setup → Email Settings** is filled in for your school, then open the sign-in
   page, click "Forgot password?", enter a staff or parent email you have on file, and confirm the
   email arrives with a working link.

## What's next

Remaining phases from your spec document:

- Dynamic Login Branding — largely already built (per-school logo/colors already apply to the
  sign-in screen via your subdomain), worth one more explicit confirmation pass.
- Final security/regression testing and deployment pass once that's done.

No need to decide now — just let me know when you want the next one started.
