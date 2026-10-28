# V91 — Dashboard Analytics, Phase 5: Student, Staff, and Parent Dashboards

Phase 5 of your "Complete Feature Enhancement Specification" document.

## The decision this round needed first: what's actually missing for Staff

Before building, I checked how the Staff Dashboard is actually served. Every non-admin role
(teacher, and any other staff position) renders through the **same** `else` branch of the
`/dashboard` route into `teacher_dashboard.html` — there is no separate staff template. That
branch already received every Phase 2-4 upgrade (gender/enrolment stats, per-class result
performance trend, pass/fail stats, Recent Class Activities) in V88-V90, scoped automatically to
whichever classes that staff member can access.

So the Staff Dashboard section of your document is, in substance, **already delivered** — it was
just built under the name "Teacher Dashboard" because that's the template every staff role shares.
I deliberately did not duplicate that work into a second code path. What I left out as explicit
follow-ups, because they need their own design decisions and aren't just a repeat of existing
building blocks:
- A staff member's own attendance-recording completion rate (how many of their expected
  attendance entries they've actually logged, vs. missed).
- Duty/timetable summaries on the dashboard itself (today's timetable already lives in its own
  page; nothing currently asked for it to be duplicated on the dashboard).
- Assigned-task completion trends — there's no general "tasks" concept for staff in the app yet,
  so this would need its own feature, not just a dashboard card.

If you want any of those, say so and I'll scope them properly rather than guessing at a shape.

## What's in this round

**Student Dashboard** — three new cards:
- **Academic Performance**: a bar-chart trend of your average score, one bar per *published*
  term only — exactly mirroring what "Published Results" already shows, so a term your school
  hasn't released never appears here either, even to you. Each bar's tooltip also shows your
  class's average that term, so you can see where you stand without ever seeing another
  student's individual mark. Below it, **Improving subjects** and **Subjects needing attention**
  compare your most recent published term against the one before it.
- **Attendance**: your attendance rate and a present/late/absent breakdown, across every day
  recorded for you.
- **Recent Activities**: a feed, but a deliberately different and narrower one than the
  Admin/Teacher feed from V90 — it only ever shows things about *you specifically* (your own
  attendance records) or things your whole class shares equally (a result just published, a new
  learning material, a school announcement). It never reuses the staff-facing activity feed,
  which would otherwise leak a classmate's score correction or registration details to your
  family.

**Parent Dashboard** — the same three cards, for the first linked child shown on the dashboard,
each one scoped only to that child's own record, with a "Full Overview"/"Details" link through to
the existing per-child pages for anyone with more than one child linked.

## Why this never leaks another student's data

Two separate guardrails, both already proven in earlier rounds and reused rather than
reinvented:
- **Publication gating**: `student_academic_performance()` only ever iterates over the exact
  `published_terms` list the dashboard route already computes — the same per-class,
  per-term `result_publication.status='published'` check that `parent_child_detail()` has used
  since it was built, not the older, coarser term-wide flag. An unpublished term is never passed
  in, so it can't appear no matter what.
- **A separate, narrower activity feed**: `student_recent_activities()` is new code, built
  specifically for this round, and on purpose does *not* call the staff `recent_activities()`
  function. It only ever selects rows already scoped to this one student's id, or to their
  class as a whole, for the few activity types that are legitimately class-wide and not sensitive
  shared with every family in that class anyway (a published result, a new material, an
  announcement they're already allowed to see).

## What I deliberately left out of this round

- **Richer trend charts** (e.g. per-subject line charts across every term, not just the two most
  recent) — the mini-bar trend plus the two-term improving/needs-attention comparison covers the
  spec's ask; a longer per-subject history is a reasonable follow-up if you want it.
- The three Staff-specific items listed above.
- A parent with more than one linked child currently only sees analytics for the first child on
  the dashboard itself (the full per-child Overview page, already built in earlier rounds,
  covers every child individually) — expanding the dashboard cards to a per-child switcher is a
  small follow-up if you'd like it.

## Database changes

**None.** Every helper this round reuses existing tables (`scores`, `attendance_records`,
`result_publication`, `result_publication_audit`, `materials`, `notifications`) with no schema
changes. No migration, no backup required before installing.

## Testing

- New suite `tests/v91_scenarios.py` (22 checks, all passing): Academic Performance respects
  publication gating (an unpublished term's scores never appear, even after being entered),
  attendance stats compute correctly, the student-scoped Recent Activities feed never leaks
  another student's event (verified with a real attendance-audit row recorded for the other
  student), a second student sees only her own data, the Parent Dashboard mirrors all of the
  above for the linked child only, improving/needs-attention subject classification is correct
  once a second term is published, and tenant isolation for a brand-new school/student.
- Re-ran `v90_scenarios.py` (15), `v89_scenarios.py` (15), `v88_scenarios.py` (16),
  `v87_scenarios.py` (63), and spot-checked `v60` (213), `v70` (39), `v75` (7), `v80` (18),
  `v85` (28), `v86` (41) — all still passing, 0 failures.

## Installing on PythonAnywhere

No database change this round, so **no backup is strictly required**, but it's always fine to
take one anyway:

```bash
cd ~/school-result-system
cp main.db main.db.bak-v91   # optional this round
```

Then:
1. Replace the changed files (or extract the new zip over your install): `app.py`,
   `templates/student_dashboard.html`, `templates/parent_dashboard.html`.
2. Reload your web app from the **Web** tab.
3. Log in as a student and confirm the three new cards appear under "Published Results" —
   Academic Performance will say "Nothing to show yet" until your school has published at least
   one term's results for that student's class, which is correct, not a bug.
4. Log in as a parent and confirm the same three cards appear for their first linked child.

## What's next

That completes Phases 2-5 of the roadmap. What's left:
- **Phase 6 (Result Display Settings — paper sizes)**: A4 Portrait (default), A4/A3 Landscape,
  A5 Portrait, Letter, Legal, Foolscap, and a Custom mm option, replacing the currently
  hardcoded A4 in `html_pdf.py`, `result-sheet.css`, and the per-template `#rsPageSize` style.
- **Phase 7 (Layout, Printing, and PDF)**: automatic layout adjustment and matching print/PDF
  pagination for every size from Phase 6.
- **Phase 8**: a final cross-cutting verification pass across everything in the document.

Let me know if you'd like me to continue with Phase 6/7 next, or reorder.
