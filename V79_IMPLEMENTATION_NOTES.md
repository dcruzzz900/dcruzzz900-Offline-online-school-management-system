# V79 — One-Page Printing: a real size floor, and a warning instead of unreadable text

This is the first piece of work from the big "Consolidated Development Specification" document
you uploaded. That document lays out a 7-phase roadmap, and I started with the phase it
recommends starting with: **One-Page Result Rendering** — because the next phase (Cumulative/Annual
Results) builds on top of it.

I went through the whole document against the live app first (not guessing), and most of it was
already in place from earlier phases (one unified login form for staff and parents, automatic
school branding by subdomain, a security-question-based account recovery flow). Two real,
confirmed gaps for this phase, below, got fixed. The rest of the document's larger items
(Cumulative/Annual results becoming term-aware, merging the separate student and admin login
pages into the one form, email-based "forgot password") are genuine future phases — bigger pieces
of work, queued up for whenever you're ready for the next round.

## 1. The size floor — the main fix

**The problem, confirmed against your spec's own rule:** *"Never shrink text below the minimum
readable size simply to force the result onto one page."* The "Fit to Page" feature (built a few
versions ago) didn't actually have a lower limit. If a result had a lot of subjects or long
comments, it would keep shrinking the text smaller and smaller — down to about **28% of normal
size** in the worst case, which is roughly 3-point text. That's not readable by anyone, printed or
on screen. And there was no warning anywhere that this had happened — a result could come out
looking fine at a glance but actually be unreadable once zoomed in or printed.

**The fix:** Fit to Page now has a real floor — it will never shrink text below about **72% of
normal size** (roughly 7.5pt off this sheet's normal 10.5pt text), which stays comfortably
readable. If a result is short enough to fit one page without going below that floor, nothing
changes — it behaves exactly as before. If a result is so long that even shrinking to the floor
still doesn't fit one page, the page is **no longer force-shrunk further**. Instead:

- The text stays at the readable floor size.
- The result is allowed to spread naturally onto a second page — nothing is ever cut off, hidden,
  or left out. (I specifically tested an overloaded result with 20 extra subjects and two very
  long comments, and confirmed every single subject and the full text of both comments are still
  present on the printed/PDF pages.)
- A yellow warning banner appears at the top of the print/preview screen — **only for whoever is
  preparing the result**, never on the actual printed page or the PDF a parent receives — telling
  them it didn't fit on one page, and suggesting what to do about it: shorten a comment, turn off
  an optional section in Result Display Settings, or lower the font size.

In practice, for the vast majority of your results — which do fit comfortably — you won't notice
any difference at all. This only changes behavior for the rare result that's genuinely too long,
and in that case you'll now get a clear heads-up instead of silently unreadable output.

## 2. A small wrong-page message, fixed

If Cumulative/Annual Results is turned off for your school, the page used to say *"Enable it under
Setup → Terms"* — but that setting actually lives under **Result Display Settings**, and has for a
while. Found this while going through the spec document; it's now a one-line message fix.

## 3. What I deliberately did NOT touch yet: automatic Portrait/Landscape switching

The spec document asks for results to automatically pick portrait or landscape based on how much
content there is. I looked into this and decided not to guess at it this round. The reason:
your result sheet lists subjects as rows going down the page, not columns going across. For a
long subject list, switching to landscape makes the page *shorter* (less room top-to-bottom) even
though it's wider — which would often make a long result print *smaller*, not bigger, defeating
the point. Doing this properly means actually measuring how much shrinking a result would need in
both portrait and landscape and picking whichever one needs less — not a rough guess based on
subject count. That's real, separate work, and I'd rather flag it honestly as a next step than
ship something that might make long results worse.

## Testing

- `tests/v79_scenarios.py` (+ `tests/test_v79_behavior.py` pytest wrapper) — new: confirms the old
  28% floor is gone and the new 72% floor is in place; confirms an ordinary result is still exactly
  one page (no change for normal cases); confirms a deliberately overloaded result (20 extra
  subjects + two long comments) produces a 2+ page PDF with every subject and the full text of both
  comments still present, nothing dropped; confirms the wrong-page message is gone and the correct
  one is there; and a real headless-browser check confirms the on-screen warning banner shows up
  exactly when it should (and only then).
- Three older tests had encoded the *old* behavior (unlimited shrink, no floor, no warning) as if
  it were permanently correct — updated to check the shape of the shrink logic rather than the old
  specific numbers, since the spec explicitly calls that old behavior wrong. Not a sign of a new
  bug, just outdated assumptions in old tests.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v79_scenarios.py`): **1,474
  checks, 0 failed.**

## Installing this update on PythonAnywhere

Normal update — no new database columns or tables, just upload and reload.

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v79.db
   ```
3. Upload the new zip and replace:
   - `app.py`
   - `templates/result_print.html`
   - `tests/v79_scenarios.py` (new)
   - `tests/test_v79_behavior.py` (new)
   - `tests/v62_scenarios.py`, `tests/v73_scenarios.py` (existing tests, updated to match the new
     behavior)
4. Go to the **Web** tab and click **Reload**.
5. Open any published student's result and confirm it still looks and prints exactly as before. If
   you want to see the new warning in action, you'd need an unusually long result (a lot of
   subjects or a very long comment) — most results won't trigger it.

## What's next

Whenever you're ready, the remaining phases from your spec document are queued up:

- **Cumulative/Annual Results** becoming aware of which term you're viewing (right now it always
  shows the whole session's total, regardless of the term selected).
- Merging the separate student login and platform-admin login pages into the one combined login
  form that staff and parents already share.
- Email-based "Forgot Username/Password" recovery (right now recovery is security-question based
  and only covers staff accounts, not parents or students).

No need to decide now — just let me know when you want the next one started.
