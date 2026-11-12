# V89 — Dashboard Analytics, Phase 3: Academic Performance Analytics

This is Phase 3 of your "Complete Feature Enhancement Specification" document (Phase 2 — Gender &
Enrolment Statistics — was V89's predecessor, V88, already installed). This round covers the
school-wide and per-class performance trends, the High-Performing/Needs-Improvement class panels,
and the teacher pass/fail statistics.

## What's in this round

**Admin Dashboard**, below the Boys & Girls card:
- **School Result Performance Trend** — a bar chart of average score (and, on hover, pass rate)
  for every term in the current academic session, up to and including the active one.
- **High-Performing Classes** — classes at or above the school's own average this term, best
  first, capped at 3, each with assessed-student count, average score, pass rate, and a simple
  ▲/▼/● trend arrow against the previous term.
- **Classes Needing Improvement** — only classes that actually trip a real, visible reason (below
  the school average, a sub-50% pass rate, or a declining trend from last term), capped at 3,
  worst first, each row says *why* it's flagged. A school with only one or two classes is never
  forced to have something show up here — see "How flagging works" below.

**Teacher Dashboard**, below the Results workspace table: a new **Class Result Performance** card
— for every class you have access to, this term's Assessed / Not Yet Assessed / Passed / Failed
counts, the class average, and a small trend chart across the session's terms so far.

## How "Passed" and "Failed" are decided

There's no separate "pass mark" setting anywhere in the app today, so I didn't invent one.
Instead, a student's **overall result for the term** is classified using the exact same
mechanism already printed on their own result sheet: their average score across every subject
they were assessed in, run through your school's own Grading & Assessments scale — the same
`grade_for()` lookup the result sheet, broadsheet, and cumulative result all already use. Whatever
grade band covers 0 in your scale (by default, **F — Fail**) is "failed"; everything above it
is "passed". If you ever change your grading scale, these statistics follow it automatically —
nothing is hardcoded to "40" or any other specific number.

A student with **no scores entered at all** this term is never silently counted as a fail — they
show up only in "Not Yet Assessed", and are excluded from the average, pass count, and fail count
entirely. Only students with at least one score contribute to the rest of the numbers.

## How flagging works (and why a single class is never flagged)

"Classes Needing Improvement" compares each class against the *school's own average this term* —
not a fixed number — plus a 50% pass-rate floor and a declining-trend check. A class only appears
if at least one of those is actually true for it. Since the comparison is against the school's own
average, a school with just one class can never end up flagging its only class (it's always
exactly at the school average, because it *is* the school average) — I tested this directly
rather than assuming it. The thresholds (50% pass rate, "below the school average") are the
"transparent thresholds" your document asked for, and they're spelled out right there in each
flagged row, not hidden in the code.

## Scope note: the trend is within the current academic session

Both the school-wide and per-class performance trends cover every term in the **current session**
(1st/2nd/3rd Term), not multiple years. A genuine multi-year trend needs its own look at how much
historical session data this app actually retains before I build something that might show a
misleadingly thin chart for older data — same reasoning as Phase 2's deferred enrolment trend.
Tell me if multi-year trend is actually what you need here and I'll scope it properly next.

## What's still queued from your document

- **Enrolment trends** (1B/2B) — still deferred from Phase 2, for the same reason.
- **Recent Activities panels** (1F/2E) — still needs the audit-log decision flagged in V88's
  notes before I build it.
- **Student, Staff, and Parent dashboard analytics** (sections 3-5).
- **The entire paper-size/orientation section** (sections 6-8).

## Testing

- New suite `tests/v89_scenarios.py` (15 checks, all passing): per-class pass/fail/average
  figures, the trend chart, High-Performing Classes, the "insufficient data" protection with a
  single class, a correctly-flagged second class once one actually underperforms, the
  not-yet-assessed/never-a-silent-fail rule, and tenant isolation for a school with no classes at
  all.
- Re-ran `v88_scenarios.py` (16 checks) and the existing regression suite — `v87_scenarios.py` (63
  checks) plus a spot-check across `v60/v70/v75/v80/v85/v86` — all still passing, 0 failures.
- No database migration in this round either — these are read-only queries over your existing
  scores/grading data.

## Installing on PythonAnywhere

Files changed this round: `app.py`, `templates/admin_dashboard.html`,
`templates/teacher_dashboard.html` (no CSS changes beyond what V88 already added — the trend
charts reuse the existing `.mini-bars` style).

1. Replace those files (or extract the new zip over your existing install).
2. Reload your web app from the **Web** tab.
3. Open the Admin Dashboard — you should see the performance trend and class panels under the
   Boys & Girls card. If no scores have been entered yet this term, you'll see the honest "No
   scores recorded yet" / "No classes with recorded scores yet this term" messages rather than
   blank space or fabricated numbers.
4. Open a Teacher account and confirm the new Class Result Performance card.

No backup strictly required (no schema change), but your usual `cp main.db main.db.bak-v89` before
reloading is fine if you'd like the habit.

## What's next

Same question as last round — tell me which to prioritize. My instinct is **Phase 4 (Recent
Activities)**, since the audit-log question it needs answering also unblocks a chunk of the
Student/Staff/Parent dashboards in Phase 5. But it's your call.
