# V81 — One Sign-In Form for Everyone

This is Phase 4 of your "Consolidated Development Specification" document: **"One Unified Login
Form for All User Roles"** and **"No School Selection on the Login Form."**

## The problem

Your main sign-in page (`/login`) already handled administrators, staff and parents together — but
students had their own separate page (`/student/login`), and the Platform/Super Admin had another
(`/platform/login`). Your spec document is explicit that this shouldn't exist:

> Do not create separate login pages for individual user roles or schools... A single login screen
> must dynamically detect the user's role.

## The fix

There is now genuinely **one page** in the whole system for signing in. Visiting `/login`,
`/student/login`, or `/platform/login` all show the exact same form — same fields, same look, same
"forgot password" and sign-up links. Whoever you are — administrator, teacher, parent, or student —
you type your username/ID and password into the same box, and the system figures out which kind of
account it is and sends you to the right place automatically. A student can type their admission
number or register number, a parent or staff member their username, email or phone — all in the
same field.

The "Class Login Code" box that first-time students use (given to them by their Form Teacher, only
needed once) is still there — it's now a small collapsible "Student logging in for the first time?"
section on the form, instead of being on a separate page.

**No change for anyone already signed in or already set up.** If your staff, parents, or students
already know how they sign in today, nothing about that changes — they just arrive at a single,
more capable page instead of being routed to one of three different-looking ones.

**The Platform Administrator (Super Admin) portal is still not advertised anywhere.** As before,
there is no button, link, or mention of it on the public sign-in page — a platform administrator
simply also uses this same form with their own username, same as always. This was a deliberate
choice carried over from your earlier requirements ("hidden from all public-facing screens"), not
an oversight.

## What changed technically (only relevant if you or your developer ever work with old bookmarks)

The old web addresses `/student/login` and `/platform/login` still work exactly as before if
someone has them bookmarked, or if some other part of the system still links to them — nothing
that depends on those addresses will break. They just now show the identical unified page instead
of their own separate-looking one, and they still accept sign-ins the exact same way they always
did. In short: old links keep working, but there's truly only one page's worth of design anywhere
in the app now.

Every security protection that existed before is still fully in place and was not loosened in any
way: account lockouts after repeated wrong attempts, protection against a very subtle timing-based
attack some login systems are vulnerable to, the "two schools share this ID" safety check, and every
school-status check (suspended, archived, expired subscription, etc.) all work exactly as they did
on the old separate pages — they were moved, not rewritten from scratch.

## What I checked and left alone

- **No school selector was added or is needed** — the system already figures out which school a
  person belongs to from their account, same as before this phase.
- **The class-code rule for first-time students is unchanged**: a student who already has a
  password set has never needed to enter a class code to sign in (it only matters the very first
  time, for account setup) — this was true before V81 and is still true now, just on the shared
  page. Entering a *wrong* code is still rejected, the same as it always was.
- **Staff and parent sign-in** is completely untouched — same fields, same behavior, same page they
  already used.

## Testing

- `tests/v81_scenarios.py` (+ `tests/test_v81_behavior.py` pytest wrapper) — new, 18 checks: all
  three addresses (`/login`, `/student/login`, `/platform/login`) serve the identical page; no
  visible link to the platform-admin portal anywhere; no school selector; a student can sign in
  directly through the unified form; a platform administrator can sign in directly through the
  unified form with a properly isolated session (no school tied to it); the old addresses still
  accept sign-ins with their original field names for backward compatibility; wrong passwords still
  fail cleanly either way; a normal student sign-in needs no class code at all, but a wrong class
  code is still rejected rather than silently ignored; staff sign-in is unaffected.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v81_scenarios.py`): **1,510
  checks, 0 failed.**

## Installing this update on PythonAnywhere

Normal update — no new database columns or tables, just upload and reload.

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v81.db
   ```
3. Upload the new zip and replace:
   - `app.py`
   - `templates/login.html`
   - `tests/v65_scenarios.py` (one stale check updated, see below)
   - `tests/v81_scenarios.py` (new)
   - `tests/test_v81_behavior.py` (new)
4. Go to the **Web** tab and click **Reload**.
5. Try it: open `/login`, `/student/login`, and `/platform/login` in turn and confirm they all look
   identical. Sign in as a student and as an admin from the same `/login` page and confirm each
   lands on the right dashboard.

(One older test, `tests/v65_scenarios.py`, had a check that looked for a link to the old separate
student page — that link no longer exists by design, so the check was updated to look for the new
in-form class-code section instead. This is just the test catching up to the intended change, not a
bug.)

## What's next

Remaining phases from your spec document:

- Email-based "Forgot Username/Password" recovery covering all account types (currently
  security-question based, and only covers staff accounts).
- Dynamic Login Branding — largely already built (per-school logo/colors already apply to the
  sign-in screen via your subdomain), worth one more explicit confirmation pass.
- Final security/regression testing and deployment pass once the remaining phases are done.

No need to decide now — just let me know when you want the next one started.
