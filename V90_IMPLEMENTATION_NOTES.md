# V90 — Dashboard Analytics, Phase 4: Recent Activities

Phase 4 of your "Complete Feature Enhancement Specification" document — the Recent Activities
panels on the Admin and Teacher dashboards, plus a full "View All Activities" page.

## The decision this round needed first

I flagged in V88's notes that the app actually has **three** separate places that already record
events — not two as I first thought once I looked closer: a generic `audit_log` table, a richer
`rbac_audit_log` used by newer settings screens, and a `security_events` table used for a handful
of signup/login events. On top of those, several specific areas already have their own dedicated,
tamper-evident history tables: `attendance_audit`, `score_audit`, `result_publication_audit`, and
`timetable_audit_v2`.

Rather than route everything through one of those (which would mean either duplicating what the
dedicated tables already do perfectly well, or weakening their append-only guarantees), **Recent
Activities reads from all of the existing sources and merges them**, newest first, into one feed.
Nothing already working was touched or risked. The only new writing I added is for the few
specific things the spec asked to show that genuinely had *no* record anywhere yet:

- Student registration and student status changes (e.g. marking someone Transferred) — these
  write to the existing `audit_log` table, which didn't have anything in it for these before.
- A parent account created directly by an admin (self-service parent signup was already logged).
- Form-teacher and subject-teacher assignments to a class — previously not logged at all.

Everything else in the feed — attendance recording/corrections, score entry/corrections, result
publication, timetable workflow, staff/parent self-signup — was already being recorded faithfully
elsewhere in the app; this round just surfaces it.

## What's in this round

**Admin Dashboard** — a new **Recent Activities** card, the 8 most recent events school-wide,
each with when, who, and what happened, plus a **View All →** link.

**Teacher Dashboard** — a **Recent Class Activities** card, the 8 most recent events, but
restricted to only the classes that teacher/staff member can actually see results for — an event
from a class they're not assigned to never appears here, even though it would on the Admin view.
This is enforced server-side, not just hidden in the UI.

**View All Activities page** (`/activities`) — every role gets this, scoped the same way as their
dashboard panel. Paginated (25 per page), with a filter by type (People, Attendance, Scores,
Publication, Timetable).

## What counts as an "activity" and where each one comes from

| Shown as | Comes from |
|---|---|
| Student registered / status changed / profile updated | `audit_log` (newly instrumented this round) |
| Parent account created (admin) / (self-signup) | `audit_log` / `security_events` |
| Form teacher / Subject teacher assigned | `audit_log` (newly instrumented this round) |
| Attendance recorded / corrected / staff check-in-out | `attendance_audit` (already existed) |
| Score entered / cleared / edited / corrected after return | `score_audit` (already existed) |
| Result status changes (Draft → ... → Published) | `result_publication_audit` (already existed) |
| Timetable workflow (submit/approve/publish/etc.) | `timetable_audit_v2` (already existed, Admin only — timetables aren't per-class in this app) |
| Learning material uploaded | `audit_log` (already existed from an earlier round) |

Nothing in this feed is invented or estimated — every row traces back to something another part
of the app already wrote at the moment it happened. A quiet school with nothing recorded yet
correctly shows "No activities recorded yet," never filler.

## Database change (small, additive, backward-compatible)

One migration this round: `audit_log` gains an optional `class_id` column, so entries that belong
to a specific class (like the new student-registration and teacher-assignment logging) can be
correctly included or excluded from a teacher's class-scoped feed. Every existing row in that
table simply gets `class_id = NULL` — nothing that already writes to `audit_log` needs to change
unless it wants to start supplying one. No existing data is touched or at risk.

## What I deliberately left out of this round

- **Richer filters** (by date range, by actor) on the View All page — type filter + pagination
  covers the core ask; date range is a reasonable follow-up if you want it.
- **Student/Staff/Parent "Recent Activities"** (sections 3-5 of your document) — these reuse this
  exact same `recent_activities()` function, scoped differently (a single student, a single
  linked child), so they should go quickly once I build the rest of those three dashboards —
  next round.
- **Parent-child link *requests*** (the pending step before an admin verifies them) still aren't
  individually logged — only the verify/reject/suspend/revoke decision is (that was already
  covered by existing code). A pending request already shows up as a notification to the admin, so
  I didn't duplicate it into the activity feed as well.

## Testing

- New suite `tests/v90_scenarios.py` (15 checks, all passing): student registration, student
  status change, teacher assignment, score entry, and a direct database check that the teacher's
  feed never shows an activity from a class they can't access, pagination/filtering on the View
  All page, and tenant isolation (including the correct empty state for a brand-new school).
- Re-ran `v89_scenarios.py` (15 checks), `v88_scenarios.py` (16 checks), `v87_scenarios.py` (63
  checks), and a spot-check across `v60/v70/v75/v80/v85/v86` — all still passing, 0 failures.

## Installing on PythonAnywhere

This round **does** touch the database schema (the new `class_id` column on `audit_log`), so
please back up first:

```bash
cd ~/school-result-system
cp main.db main.db.bak-v90
```

Then:
1. Replace the changed files (or extract the new zip over your install): `app.py`, `db.py`,
   `templates/admin_dashboard.html`, `templates/teacher_dashboard.html`, and the new
   `templates/activities_list.html`.
2. Reload your web app from the **Web** tab — the migration runs automatically on first request,
   the same way every migration on this project always has.
3. Open the Admin Dashboard and confirm the Recent Activities card appears (it'll be empty until
   something new happens, since it only shows real events going forward for anything that wasn't
   already logged before this round).
4. Try **View All →** and the type filter.
5. Open a Teacher account and confirm Recent Class Activities only shows their own classes.

## What's next

Per the roadmap, **Phase 5 (Student, Staff, and Parent dashboard analytics)** is next, and now
that Phases 2-4 exist it should move faster — it's largely the same building blocks
(`student_gender_stats`, `class_term_result_stats`, `recent_activities`), scoped to one student or
one linked child at a time instead of a whole class or school. Let me know if you'd like me to
continue there, or reorder toward the paper-size/orientation section instead.
