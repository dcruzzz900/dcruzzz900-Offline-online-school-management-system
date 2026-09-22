# One app, online and offline

Staff use **one interface**. After logging in they land in the app (`/app`; `/dashboard`
and the PWA start page redirect there) and use the same dashboard, navigation, forms, score
entry, attendance, results, broadsheets, reports and settings whether or not there is a
connection. There is no separate "offline mode" to switch to.

- **Local first.** Every screen reads and writes this device's own copy of the school's
  data (IndexedDB, one database per school). Saving an entry never waits for the network.
- **Automatic sync.** Changes are sent to the server by themselves — right after each save
  when online, when the connection returns, and on a timer — and other people's changes come
  back the same way. Nobody uploads a file. After a sync the server is up to date and the
  device keeps its copy for continued offline work.
- **Verified connectivity, no manual modes.** `static/js/connectivity.js` runs in the
  background and asks the server a tiny question (`GET /healthz` → `{"status":"ok"}`) instead
  of trusting the browser's "online" flag, which only means a network interface is up. A
  refused connection, a timeout, or a captive-portal/login page in place of the answer all count
  as "not reachable". Two failed checks in a row (or the browser reporting no network at all)
  switch the app to offline; one good answer switches it back and starts a background sync.
  While offline it re-checks after 2, 4, 8, 15, 30 s (then every 30 s), so recovery is noticed
  within seconds; while online it checks every 15 s, and immediately after any network error
  from the sync engine. The service worker never answers `/api/*` or `/healthz` itself, so a dead
  connection can't look alive. The screens, layout and workflow don't change between modes — only
  the indicator does (and the few server-only pages, which show a "connection lost — return to the
  app" notice). Tests: a fake-network/fake-clock unit test, and real-browser tests where the server
  is unreachable while the browser still says it's online, where a captive portal answers everything
  with 200 HTML, and where the server comes back and the entry syncs by itself.
- **Connection indicator.** One small pill in the top bar: 🟢 Online — Synced ·
  🟠 Offline — Saved Locally · 🔄 Syncing (tap it for details, conflicts and backup). It
  shows "🟠 n to review" only when a change needs a person (a conflict or a refused entry).
- **First-time device setup.** The first login on a device downloads the school's data
  (with a progress screen) so it works offline from then on; it happens by itself.
- **Multi-school isolation.** The server only ever sends a device its own school's data
  (tested: cross-school reads/writes are refused on every route and on the sync API). On the
  device, each school has its own database and each saved login opens only its own school. A
  test signs into two schools in one browser, online and offline, and checks that neither
  ever shows the other's data. Note that a school's cached data stays on the device after
  logout (it must, for the next offline session), protected by the phone's own security.
- **Conflicts.** See section 7: edits to different fields merge, the same field is flagged
  for a person, nothing is silently overwritten, and every change is in the audit trail.

**What is in the app (works offline):** Dashboard (admin and teacher), Classes → Results &
Broadsheets (view, print, save as PDF, CSV/Excel) including the cumulative (whole-session)
broadsheet, My Class / Attendance and Roll-Call History, Staff Attendance (with history),
Score Entry,
Teacher & Principal Comments, Student Registration, Students (search, edit), Assign Subjects,
Classes, Subjects, Teachers/Staff (add, edit, reset password), Grade bands (add/edit), Notifications (read),
Import/Export, Learning
Learning Materials (all the ones you may see are listed; save chosen files for offline use, open them
with no connection), Settings (school info, score weightings, grade bands), Sync Status.

**Still server pages (same menu; offline they say "needs an internet connection"):** Terms &
sessions, Promote Students, Sending notifications, Change password / recovery, School profile &
logo, Removing a grade band, Email settings, Materials upload/removal,
the per-student score-history page, the server-made PDFs (the app prints/saves PDFs from the device instead), the Super Admin
(platform) pages and the student portal. Bringing these into the app is the remaining
work toward a single, fully offline UI; the ones that change things for the whole school at
once (promotion, terms) are deliberately online-only because they can't be merged safely
after the fact.

---

# Offline-First Architecture

This document describes what was built, how it works, what its security
model relies on, and — importantly — **what is not done yet** and how to
extend it. Read this before treating the feature as "finished."

## Honest scope statement

The requirements describe full offline parity across the entire
application (every school function, from student registration to
comments to result printing). This codebase is a ~4,500-line
server-rendered Flask app (Jinja templates, no client-side framework).
Turning *every* one of its ~40 templates into a client-rendered,
IndexedDB-backed view is a large, multi-week undertaking on its own —
each screen has its own business logic (grade computation, promotion
rules, PDF generation, etc.) that would need to be either duplicated in
JavaScript or restructured.

What's implemented here is a **complete, working, production-quality
foundation** — the hard, easy-to-get-wrong parts (encrypted offline
login, tenant-isolated local storage, a generic conflict-aware sync
engine, server-side authorization that can't be bypassed by a
compromised client) — plus **three fully working offline workflows**
(attendance/roll call, score entry, student registration) built on top
of it, end to end, tested. Extending it to more screens is now a
mechanical, well-documented process (see "Adding another offline
screen" below), not an architectural one.

## Architecture

```
Online Server (Flask/SQLite)
        ↕  /api/offline/*  and  /api/sync/*   (sync_api.py)
Synchronization Engine (static/js/sync-engine.js)
        ↕
Secure Local Database (IndexedDB, static/js/offline-db.js)
        ↕
School App (templates/offline_app.html + static/js/offline-app-ui.js)
```

### 1. Offline login

- **Opening the app with no connection.** The installed app's start page (`/dashboard`),
  `/` and `/login` go straight to the offline app when the network can't be
  reached, or doesn't answer within 8 seconds (`service-worker.js`). The
  offline app asks for the person's **password** — the same one they use online —
  and with one account on the device goes directly to the password box.
  ("Log in online instead" links to `/login?online=1`, which the service worker
  doesn't redirect.)
- **Setup is automatic.** Every ordinary online login runs
  `OfflineAuth.provisionAfterLogin()` while the password is still in memory
  (`templates/login.html`): it calls `POST /api/offline/enroll` (for a returning
  person on this device, with the same device id, so nothing they have queued is
  disturbed), and encrypts `{device_id, device_secret, user}` with a key derived
  from their password (PBKDF2, 600k rounds; AES-GCM, so a wrong password fails
  loudly). The dashboard then downloads the school's data in the background the
  first time. Nothing is stored in plain text; the server keeps only a hash of
  the device secret. Changing your password takes effect offline at your next
  online login, which re-wraps the credential. (Settings → Offline Access still
  lets someone already logged in set the device up by confirming their password.)
- **Unlock throttling.** After 5 wrong passwords the lock screen makes you wait
  (30 s, doubling, up to 15 min). The real protection against someone copying
  the browser's storage is the password's strength and the 600k-round derivation.
- **Session expiry / security controls** (`offline-auth.js`):
  - *Short* — an unlocked session lasts `MAX_SESSION_HOURS` (12h) **or** until
    the tab/browser closes (`sessionStorage`), whichever is first. Logging out
    online also locks it.
  - *Long* — the credential hard-expires after
    `OFFLINE_CREDENTIAL_LIFETIME_DAYS` with no successful contact with the server
    (default **30**; set `OFFLINE_CREDENTIAL_DAYS` to change, 7–365). Every
    successful sync or check slides it forward. When it has expired the offline
    app still asks for the password, then explains that one online login renews
    access and that everything entered is still saved — see "A device that has
    been offline for weeks" below.
- **Revocation.** The server refuses a device whose credential is expired or
  revoked, whose person is deactivated or deleted, or whose school is suspended
  or archived, and says **why** (`status` in the 401 body) so the app can show
  the right message and keep the person's work. Deactivating a staff account,
  deleting it, an admin password reset, or suspending the school revokes the
  affected devices immediately. A device's role is read from the person's
  current record on every request, never from a snapshot. A person's oldest
  devices are switched off beyond 10 live ones.
- A device id can only be renewed by the person it belongs to (re-enrolling
  someone else's id issues a new id instead).

### 2. Offline functions

Implemented end-to-end, working with zero connectivity, from a device
that has enrolled at least once:

- **Attendance / roll call** — pick class + date, mark present/absent,
  saves locally and syncs later.
- **Score entry** — pick class + subject (scoped to what that teacher
  actually teaches), enter CA1/CA2/Exam per student.
- **Teacher / principal comments** — pick a class, write each student's
  comment(s); a teacher only sees/can set the teacher's comment field
  (the principal's comment field is hidden client-side AND stripped
  server-side if a non-admin tries to set it anyway — see
  `_restrict_principal_comment` in `sync_api.py`).
- **Student registration** — add a new student while offline.
- **Class management, subject management, teacher/staff management**
  (admin/sub_admin only) — add new classes, subjects, and staff accounts
  offline. Passwords are hashed server-side on sync and never stored
  in plaintext locally once synced (see below); role escalation is
  blocked server-side (an offline "add teacher" can't mint an admin or,
  unless the caller is the main admin, another sub-admin — see
  `_hash_password_before_write` in `sync_api.py`).
- **Sync status & conflict resolution** — see pending/failed/conflicted
  counts per entity, manually resolve a conflict ("keep mine" /
  "keep server's").

Reference data needed to drive these screens (classes, subjects,
sessions, terms, the teacher↔class↔subject map) is synced read-only, so
dropdowns work fully offline too.

Also available offline (added in the multi-school/multi-device release):

- **Results & broadsheets** — totals, averages, grades and class positions are
  worked out on the device (`static/js/offline-results.js`, tested to give the
  same numbers as the server). Result sheets and broadsheets can be viewed,
  printed and saved as PDF through the browser's own print dialog.
- **CA3 (optional)** — a school turns it on by setting a CA3 maximum above 0
  under Grading Setup; devices pick this up on their next sync.
- **CSV and Excel (.xlsx) import/export** — students and scores, validated
  the same way the server validates them (`offline-results.js`,
  `static/js/xlsx-lite.js`, no internet or library download needed).
- **Learning materials** — anything saved with "Save offline" on the online
  Learning Materials page is listed and opens offline (`offline-materials.js`).
- **School & grading settings** — school admins can change the maximum marks
  offline (same rules as online: no negatives, total no more than 100, never
  below a mark already saved). The grade bands (A, B, C…) are edited online.
- **Staff** — add teachers/staff, edit name/position, and reset a password
  offline. Passwords are hashed *on the device* (PBKDF2, in the format the server
  already checks); the plaintext is never stored or queued. Sub-admins can manage
  teachers only, exactly as online.
- **Class arms** — enter a level ("JSS 1") and arms ("A, B, C") to create
  "JSS 1 A", "JSS 1 B", "JSS 1 C" in one go, online or offline. Results still use
  the class name, so nothing else changes for existing classes.
- **Skills ratings, signed dates and auto-generated comments** appear on the
  offline result sheet, computed the same way as the server (the parity test
  covers them).

**Not built as offline screens** (server-rendered only): promotions, entering
skills ratings, editing the grade bands, and email/payment/AI features, which
genuinely need the internet. The server's own ReportLab PDFs also need the
server; the offline route is browser print → Save as PDF.

### 3. Automatic synchronization (`static/js/sync-engine.js`)

- Every offline-created/edited record gets a client-generated UUID
  (`client_uuid`) at creation time. This is the idempotency key for the
  entire sync round-trip: retrying a push after a dropped connection
  re-upserts the same row instead of creating a duplicate. Verified by
  test: pushing the same `client_uuid` twice produces exactly one row.
- **Push**: batches pending/failed local records to `POST
  /api/sync/push`. Each record carries `base_updated_at` — the
  `updated_at` value this device last saw for that row. If the server's
  current value has moved on since then, the push is rejected as a
  **conflict**, not silently overwritten in either direction; both
  versions are kept (locally, and in the server's `sync_conflicts`
  table) for the user (or an admin) to resolve. Verified by test.
- **Pull**: `GET /api/sync/pull?since=<timestamp>` returns everything
  changed since the last sync, scoped to the caller's school and role.
- **Retry**: failed pushes back off exponentially per record
  (`5s × 2^attempts`, capped at 5 minutes) so one broken record doesn't
  get hammered every cycle, but is still retried automatically. Auto-sync
  runs on the `online` event and every 60s while online.
- **Status display**: a nav badge (`base.html`) and a dedicated screen
  (`offline-app-ui.js`'s Sync Status view) show pending/conflict/failed
  counts, driven by a `offline-sync-status` DOM event. Unresolved
  conflicts are also visible to admins school-wide (not just on the
  device that caused them) at **Settings → Review Sync Conflicts**
  (`/admin/sync-conflicts`), where an admin can apply the offline
  device's version or keep the server's.

### 4. Multi-school data isolation

- **Client-side**: each school gets its **own IndexedDB database**
  (`srs_offline_school_<id>`), not just a filtered view of a shared one.
  Two different schools' staff using the same physical device end up
  with two databases that no query can accidentally join across.
- **Server-side**: `sync_api.py`'s `resolve_identity()` derives
  `school_id` *only* from the authenticated session or verified device
  credential — **never** from anything the client sends. Every write
  path re-validates that the record's own foreign keys (e.g. a score's
  `student_id`) resolve to a class in that same school before touching
  the database. Verified by test: a device credential from School B
  attempting to write into School A's class is rejected with
  `cross-school write rejected`.
- Per-role scoping on top of that: a teacher's reads/writes are further
  restricted to the classes they're the form teacher of (attendance,
  student records) or teach a subject in (scores) — see the
  `ENTITIES` registry in `sync_api.py`.

### 5. Functions requiring internet

Email delivery, PDF generation for printing/download, payments, and
Super Admin operations still require the server — that part is
unchanged. What's new: **email delivery is now queueable while offline**,
as a proof of the "queued where possible and automatically processed
when the connection returns" requirement.

- A device queues the *request* (not the data) locally — e.g. "email
  Class 3B's results to parents" — via `SyncEngine.queueAction()`
  (Offline App → Queue Internet-Only Actions). There's no local approximation
  of sending an email; the request just waits.
- The next successful sync calls `POST /api/actions/queue`
  (`app.py`), which — since that call only ever happens while online —
  performs the action for real: it reuses the exact same
  `send_class_results_emails()` helper the normal online "Email Results"
  button calls, so the two paths can't drift apart.
- Every attempt is logged in `deferred_actions` (school, device, action
  type, payload, status, result message), including failures — so
  there's an audit trail of what got queued and what happened to it.
- Idempotent by `client_uuid`, same as data sync: replaying a queued
  action (e.g. because the response to a previous attempt was lost)
  returns the already-recorded result instead of sending the emails
  twice — verified by test.
- Authorization is re-checked server-side against the resolved identity
  (same `can_view_class_results` check the online route uses), not
  trusted from the queued payload — verified by test that a teacher
  without access to a class is rejected even though the request reached
  the endpoint.
- Only one action type (`email_class_results`) is wired up. Extending
  this to other internet-only functions (payments, AI features, cloud
  backups) means adding a new entry to `DEFERRED_ACTION_TYPES` and a
  branch in `_process_deferred_action()` in `app.py` — the queueing,
  retry, idempotency, and audit-log machinery is already generic.

## Adding another offline screen

1. **Server**: if the table isn't already in `ENTITIES` in `sync_api.py`,
   add an entry (fields whitelist, school-scoping function, role
   permissions). If it needs `client_uuid`/`updated_at`/`is_deleted`
   columns, add it to the `syncable_tables` list in
   `migration_024_offline_sync` (`db.py`) — write a new migration
   function rather than editing that one once it's shipped.
2. **Client**: add the entity name to `ENTITY_STORES` in
   `offline-db.js` (bumps nothing — IndexedDB stores are created
   lazily on next DB open per school; existing users get it
   automatically since the version number only needs to change if you
   alter *existing* stores, not add ones nobody has opened yet — to be
   safe, bump `SCHOOL_DB_VERSION` when adding a store).
3. Build the screen in `offline-app-ui.js` (or split into its own file)
   using `OfflineDB.getAll()` for reads and `SyncEngine.queueChange()`
   for writes — follow the pattern in `renderAttendance`/
   `renderScoreEntry`.
4. Nothing else needs to change — push/pull/conflict handling is fully
   generic.

### 6. Pagination (bootstrap / pull at scale)

`bootstrap`/`pull` are cursor-paginated (`sync_api.py`'s `PAGE_SIZE`,
500 rows/entity/page by default, capped at `MAX_PAGE_SIZE`=2000). Scoping
(tenant isolation + per-role visibility) is expressed directly in SQL via
joins (`_scoped_sql`) rather than fetched-then-filtered in Python — this
is what makes LIMIT/OFFSET pagination actually correct: filtering after
the fact would make "page 3" mean a different, shifting set of rows
depending on how many got excluded by the scope check on earlier pages.
`SyncEngine.bootstrap()`/`pullDeltas()` on the client loop on the
returned `cursor` until every entity is exhausted. Verified by test: 28
students paginated at page size 10 (3 pages) are collected exactly once,
with no gaps or duplicates.

**A genuinely important bug this surfaced and fixed**: this app's
*existing* online routes (add student, add class, enter scores, take
attendance, add comments — all written before offline sync existed)
never set `client_uuid`/`updated_at` on insert, and never bumped
`updated_at` on update. Two real consequences: (1) a record created
through the normal UI would have `client_uuid IS NULL`, which is not a
valid IndexedDB key — bootstrap would break trying to store it; (2) an
online edit that didn't bump `updated_at` would look "unchanged" to the
conflict check, so a stale offline edit could silently overwrite it
without being flagged as a conflict. Auditing every INSERT/UPDATE site
across a 4,500-line app to fix this by hand would be fragile — easy to
miss one, easy for a future route to reintroduce the gap. Fixed instead
with SQLite triggers (`migration_026_sync_triggers` in `db.py`) on every
syncable table: an `AFTER INSERT` trigger fills in `client_uuid`/
`updated_at` if the inserting statement left them NULL, and an
`AFTER UPDATE` trigger bumps `updated_at` — but only
`WHEN NEW.updated_at IS OLD.updated_at`, i.e. only when the UPDATE
statement didn't already set it itself, so it never clobbers the exact
value `sync_api.py`'s push endpoint computes and returns to the client.
This protects every code path, present and future, sync-aware or not —
verified by test (a bare INSERT/UPDATE with no offline-sync awareness at
all, exactly mimicking what the existing routes do, correctly gets
`client_uuid` filled in and `updated_at` bumped either way).

## Real-browser verification

Everything above was, until this pass, verified only through Flask's
test client and Node-based logic harnesses — thorough for correctness,
but not the same as a browser actually running the service worker,
IndexedDB, and WebCrypto. This was closed out with Playwright driving a
real headless Chromium against a live copy of this app. (A caution learned
later: Playwright's `set_offline(True)` does not stop a *service worker's* own
requests, so it can make a test look offline when the worker is still reaching the
server. The current tests instead switch the test server off, so connections are
really refused — see `tests/helpers.py: LiveServer`.) Confirmed, for real:

- Enrollment, password encryption, and service worker install all complete
  successfully in a real browser (`navigator.serviceWorker.ready`
  resolves, `registration.active.state === "activated"`).
- A wrong password is rejected (AES-GCM decryption genuinely fails) and the
  correct password works right after.
- `/offline-app` loads with **zero network** on a cold navigation —
  proof the service worker precache actually works, not just in theory.
- A class and a student registered into it, in the same offline
  session, both sync correctly on reconnect with the student's
  `class_id` resolved to the class's real server id (the dependency-safe
  creation feature, end to end, in a real browser).
- A hard page reload while still offline preserves both the unlocked
  session (via `sessionStorage`, which survives a reload — it's cleared
  only on tab/browser close) and all local IndexedDB data.

This process found and fixed two real bugs that no amount of headless
logic testing would have caught:

1. **Success messages were invisible.** The class/subject/teacher
   management screens called a full-screen re-render immediately after
   setting their own "Saved" message, wiping it out before it could ever
   be seen. Fixed by refreshing only the results list in place (matching
   the pattern already used correctly by Attendance/Score Entry),
   leaving the form and message untouched.
2. **A not-yet-synced class could leak into the wrong screens.** A class
   created offline (no server id yet) correctly shows up — labeled "not
   yet synced" — in Student Registration and Class Management, where
   dependency-safe creation is the point. But it was also appearing in
   Attendance, Score Entry, and Comments, where it doesn't belong: those
   are tied to a class by a plain foreign key with no pending-ref
   resolution, so selecting it would silently try to save a record with
   `class_id: undefined`. Fixed by filtering those three screens to
   already-synced classes only, with a message telling the user to
   connect once online first (or use Manage Classes and wait for it to
   sync) — the same boundary already established correctly in the
   Actions Queue screen.

## Scale: how much a phone downloads

Measured with a synthetic 1,263-pupil school (20 classes, 15 subjects, a term of daily
attendance = ~100,000 rows): a first-time download is ~23 MB of JSON, ~3 MB on the wire
(sync answers are gzipped when the client asks), in 38 requests / a few seconds server time.
Two things keep it that way:

- **Data window.** A device receives the active session's scores, comments and skill ratings and
  the active term's attendance; earlier sessions stay on the server (their result pages are
  online pages), and the Results screen only offers the current session. When the school moves
  to a new term or session the app notices (on its next sync), downloads the new window and
  drops the old one — never touching anything not yet synced (`sync_api._WINDOWED`,
  `SyncEngine.currentWindowKey`).
- **Paging.** Cursors remember which entities are finished. (A bug — finished entities being
  re-sent from row 0 on every page — once made this same download ~450 MB / 2 million rows; a
  regression test now guards it.)

Not measured: IndexedDB behaviour with several hundred thousand records on low-end phones, or
first-time download over a genuinely slow mobile network — worth checking in a pilot.

## 7. Multi-device conflict rules, audit trail and deletions

Every queued change carries a **change ID** (unique per edit), the device's
timestamp, its device ID and the values the device last synced (`base_data`).
The server derives the school and user from the device credential, never from
the request body. Rules are in `sync_rules.py`; each entity's policy is set
in `ENTITIES` in `sync_api.py`.

| Situation | Result |
|---|---|
| Nobody else changed the row | applied |
| Another device changed **different fields** (students, scores, comments, classes, subjects) | field-level merge: both edits kept, recorded as `merged` |
| Another device changed the **same field to a different value** | conflict; nothing overwritten; both versions kept for a person to resolve |
| Two devices created the same student/subject/term score cell offline | one row; merged if they filled different fields, conflict if the same field |
| Attendance marked differently on two devices | the later edit wins (device clock clamped to server time + 5 min), the loser is kept in the audit trail |
| Staff accounts | any concurrent change is a manual conflict |
| Edited offline, but deleted online meanwhile | conflict ("keep mine" puts it back) |
| Same change ID pushed twice (dropped connection) | applied once |

- **Audit trail:** `change_audit` records who/which device/when/old→new/outcome
  for every applied, merged, superseded, refused or conflicted change (passwords
  are redacted). Admins can read it at `/api/sync/audit`. Synced score edits also
  go into `score_history` like online edits.
- **Deletions:** the online screens hard-delete rows. Database triggers now record
  each deletion in `sync_tombstones` (scoped to its school) and devices drop those
  records on their next pull. Deleting *through* sync is refused.
- **Versioning:** `updated_at` is the row's version token and is now strictly
  increasing per row, so two edits in the same second can't hide each other.
- **Validation on push:** the server re-checks max marks (CA3 only when enabled),
  attendance status/date, that every foreign key belongs to the caller's school,
  role/scope, and that record IDs have a harmless format.
- **What devices are never sent:** password hashes, security-question answers and
  student login credentials.

## 8. A device that has been offline for weeks

What happens, in order (all covered by tests, see "Tests" below):

1. Work is saved on the device as normal — hundreds or thousands of queued
   changes are fine. Refused-by-the-server changes are retried a few times, then
   left for the person to correct, retry or discard.
2. Past the credential lifetime the lock screen still accepts the password, then
   shows "log in online once to renew — everything you entered is still saved
   here". Nothing is deleted, ever, by expiry.
3. Back online, the person logs in normally. That renews the **same** device
   (new secret, same id), and the dashboard syncs: changes are pushed first, so
   the server can combine two people's edits to different fields, flag a real
   clash, or refuse changes for records deleted meanwhile (they appear under
   "failed", with the reason).
4. A full re-download can never overwrite unsynced work; it only replaces what is
   already synced, and removes records that were deleted online or that this
   account can no longer see.
5. A change is pushed under the credentials of the person who made it. On a
   shared device, another person's unsynced work waits until they unlock and sync.
6. Safety net for the browser's own storage: the app asks the browser not to
   clear its data, warns when unsynced work exists and that hasn't been granted,
   and **Sync Status → Download backup** saves every unsynced change to a file
   (Restore puts them back without overwriting anything newer).
7. If access was turned off in the meantime (account deactivated, school
   suspended), the app shows the reason, keeps everything queued, and the backup
   button is the way to preserve the work.

## 9. Shared devices

Cached pages are stored per URL. To stop one person's cached pages being served
to the next person on a shared device, the pages ask the service worker to
forget cached pages on logout and when a different user signs in, and to forget
saved learning materials too when a different *school* signs in
(`purge-pages` / `purge-all` messages in `service-worker.js`). The offline app's
own data is in a separate IndexedDB database per school.

## Security notes / limitations to know about

- The offline PIN is a **local convenience credential**, not a
  replacement for full-disk encryption. It stops a stolen device from
  being logged into via the encrypted blob alone, but doesn't protect
  against someone with a debugger session on an *unlocked* browser.
- A new teacher/staff password entered offline (Manage Teachers / Staff)
  sits in the local IndexedDB record in plaintext until it syncs — it's
  hashed server-side (`_hash_password_before_write`), and the plaintext
  is deleted from the local record the moment sync succeeds
  (`pushBatch` in `sync-engine.js`). Until then, it's protected only by
  the same PIN-encrypted-at-rest boundary as everything else on the
  device — flagged here explicitly since it's a materially different
  sensitivity level than a score or an attendance mark.
- `sessionStorage` for the unlocked session means the offline session is
  gone on tab/browser close by design (re-enter PIN) — this is
  intentional, not a bug, per the "offline-session expiry" requirement.
- The push endpoint caps a batch at 500 changes; a device with a very
  large backlog will need multiple sync cycles (the engine already
  batches in groups of 50 client-side, well under that limit).
- `bootstrap`/`pull` are cursor-paginated (see "Pagination" above) —
  this was the one item flagged as a known gap in an earlier pass, and
  is now fixed and tested.
- Tests: `python tests/run.py` runs server tests (Flask test client against
  the real schema/migrations), a parity test (offline result engine vs the
  server's numbers), the real client sync engine against a live server with two
  simulated devices, `.xlsx` checks against openpyxl, and a real-Chromium test
  (service worker, IndexedDB, going offline with the server truly unreachable,
  opening the app straight into the offline password box, hanging connections,
  a phone offline for 40 days locked locally then renewed by one login with no
  work lost, CA3 score entry, Excel import/export, saved materials, reconnect and
  sync), a 720-change "offline for weeks" scenario against a live server, and
  upgrades of databases from both earlier builds. Needs `node`; the browser tests
  are skipped when Playwright/Chromium isn't installed. Not yet
  tested: physical phones/tablets, iOS Safari (PWA storage rules differ),
  long-running low-storage behaviour, and multiple gunicorn workers (unsupported).
- Known limits: an unlocked offline session's plaintext new-staff password sits in
  IndexedDB until it syncs (see above); ties in class position get sequential
  positions in surname order, matching the existing online behaviour; a device
  that stays offline longer than the credential lifetime (~3 weeks) must be
  re-verified online.
- The offline password protects the saved login on the device (it is the person's normal password, so it is only as strong as that). It does not encrypt the school data cached in the browser: anyone who can open the phone's browser storage can read it, so use the phone's own screen lock and device encryption.
- Untested on real hardware: phones, tablets, iOS Safari (which can clear a site's storage after a week of non-use unless the app is added to the home screen — hence the backup button).
