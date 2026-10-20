# V80 — Cumulative/Annual Results now follow the term you're actually looking at

This is Phase 3 of your "Consolidated Development Specification" document — the phase right after
one-page printing (V79), which the document itself says should come next because Cumulative/Annual
Results depend on it.

## The problem

Your spec document is specific about how this should behave:

> First Term: Display only First Term results. Second Term: Display First and Second Term results
> together. Third Term: Display First, Second, and Third Term results together.

The Annual/Cumulative Result page didn't do this. It always combined **every term in the session
that had any scores entered**, no matter which term you were actually looking at when you clicked
into it. So viewing the cumulative result from First Term and from Third Term showed the exact same
thing — whatever had been entered so far — rather than "everything up through First Term" versus
"everything up through Third Term."

## The fix

The Annual/Cumulative Result page and the Annual/Cumulative Broadsheet now both have their own
**"Through term"** selector (next to the existing Session selector), and consolidate only up
through whichever term is chosen:

- Pick **First Term** → only First Term's figures are shown/averaged.
- Pick **Second Term** → First and Second Term together.
- Pick **Third Term** → all three terms together.

Clicking through from an ordinary result sheet or broadsheet now takes you straight to the matching
cumulative view — the "View cumulative result" and "Annual / Cumulative Broadsheet" buttons on the
First Term page land you on the First-Term-only cumulative view, Second Term's buttons land you on
First+Second, and so on — so in normal use you won't usually need to touch the new selector at all,
it's there for when you want to look back at an earlier cutoff deliberately.

**A later term is never averaged in early**, even if its scores happen to already be entered (e.g.
a teacher got ahead and typed in Second Term scores while First Term's cumulative is still what's
being viewed) — it simply doesn't appear until you select up through it.

**A genuinely missing term's score is still never treated as a zero.** If a subject has no score
for a term that's within the selected range (say, it just hasn't been entered yet for Second Term,
even though you're viewing "through Second Term"), that subject's cumulative average is still
calculated only from the term(s) that do have a score — it's shown as "-" for the missing one, not
averaged in as 0 and dragging the figure down.

If you don't specify a term at all (an old bookmark, or just visiting the page directly), it now
falls back sensibly to that session's own active term rather than silently mixing everything —
this only matters if you're navigating there by hand rather than clicking the normal links.

## What I checked and left alone

- **How the totals/averages/positions are calculated** — unchanged. Your cumulative average is
  still the mean of each subject's totals from the included terms (not a simple addition of term
  averages), and class positions still use the same tie-aware ranking as everywhere else in the
  app. There's no school-configurable "calculation method" setting anywhere in the app today, so
  there was nothing further to make "follow the school's configured rules" — this already is the
  one rule that exists.
- **Publication/approval permissions** — unchanged and already correct: the same role-based access
  check that gates the ordinary result/broadsheet pages (only admin/principal/VP/exam officer/that
  class's own form teacher) also gates the cumulative pages.
- **Who can see the Cumulative/Annual Result** — still staff-only (admin/teacher roles), as it was
  before. Your spec document doesn't explicitly ask for parents/students to get their own cumulative
  view, so I didn't add one — flagging this as a scope call, not something you asked for. If you'd
  like parents/students to be able to view cumulative results too, that's a reasonable small
  follow-up.
- **Full Result Display Settings customization on the cumulative pages** (your own logo colors,
  fonts, etc., the same way the regular result sheet already respects them) — this page still uses
  its own simpler, fixed layout, same as before this phase. It's a separate, smaller piece of work
  than "which terms get consolidated," and I didn't want to blur the two together in one round —
  flagging it as a known follow-up if you want the cumulative pages to visually match your branded
  result sheets.

## Testing

- `tests/v80_scenarios.py` (+ `tests/test_v80_behavior.py` pytest wrapper) — new, 18 checks: First
  Term selected shows only First Term; Second Term shows First+Second but never leaks Third Term
  even though it exists; Third Term shows all three; a genuinely missing (not future) term's score
  is excluded from the average rather than counted as zero; disabling Cumulative/Annual blocks the
  page; omitting the term selector falls back to the session's active term; the class broadsheet's
  computed averages actually change between cutoffs (80.0 through First Term alone vs. 60.0 through
  First+Second); the PDF route honors the same cutoff; and the "View cumulative result"/"Annual /
  Cumulative Broadsheet" links from the ordinary result/broadsheet pages are wired to the term being
  viewed.
- `tests/v68_scenarios.py` (existing, 2 checks updated with an explanatory comment): its two-term
  cumulative-tie checks now pass the term explicitly (`?term_id=...`) to get the same "consolidate
  through Second Term" result they always expected — not a sign of a bug, just this test needing to
  say explicitly what it wants now that the page actually distinguishes between terms.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v80_scenarios.py`): **1,492
  checks, 0 failed.**

## Installing this update on PythonAnywhere

Normal update — no new database columns or tables, just upload and reload.

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v80.db
   ```
3. Upload the new zip and replace:
   - `app.py`
   - `templates/cumulative_result.html`
   - `templates/cumulative_broadsheet.html`
   - `templates/result.html`
   - `templates/broadsheet.html`
   - `tests/v80_scenarios.py` (new)
   - `tests/test_v80_behavior.py` (new)
   - `tests/v68_scenarios.py` (2 checks updated, see Testing above)
4. Go to the **Web** tab and click **Reload**.
5. If you use Cumulative/Annual Results: open a published First Term result for a student who also
   has Second/Third Term scores entered, click "View cumulative result," and confirm it shows only
   First Term — then go back and try it from a Second or Third Term result to see the figures
   widen to include the earlier terms too.

## What's next

Remaining phases from your spec document, still queued whenever you're ready:

- Merging the separate student-login and platform-admin-login pages into the one unified login
  form staff and parents already share (no school selector, automatic branding by subdomain —
  these are mostly already built, the remaining piece is folding those two separate pages in).
- Email-based "Forgot Username/Password" recovery (currently security-question based, and only
  covers staff accounts).
- The two smaller follow-ups noted above: cumulative results for parents/students, and full Result
  Display Settings customization on the cumulative pages.

No need to decide now — just let me know when you want the next one started.
