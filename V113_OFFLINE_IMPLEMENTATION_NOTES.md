# V113 — Offline-first support (SQLite stays primary; no PostgreSQL/Neon)

## What was added (nothing existing was rewritten)
| Piece | File | Role |
|---|---|---|
| Service worker | `static/service-worker.js` | Caches the app shell + the pages the signed-in user opened; offline fallback page `/offline`. Never caches `/api`, login/logout, `/platform`. |
| Offline engine | `static/js/offline/offline-core.js` | IndexedDB queue, AES-GCM encryption (non-extractable key), server-reachability detection, replay with retry/back-off, conflict & failure handling. |
| Offline UI | `static/js/offline/offline-ui.js`, `static/css/offline.css` | Status pill (Online / Offline / Synchronizing / Sync Completed / Sync Failed), offline form queueing, logout safety, Sync Center panel. |
| Server | `offline_sync.py` | Idempotent replay (`sync_changes`), conflict detection (`sync_conflicts`), status/report/resolve APIs, `/sync` page, `/offline` page. |
| Schema | `db.py` `migration_089_offline_sync_v113` | Additive only; plain TEXT/INTEGER columns (portable to PostgreSQL later). |
| Local install | `run_local.py`, `local_backup.py` | One-computer SQLite installation, automatic verified backups, restore. |
| Pages | `templates/sync_center.html`, `templates/offline.html` | Sync Center (all staff: this device; admins: conflicts + audit) and offline page. |
| Tests | `tests/v113_offline_scenarios.py` (64), `tests/v113_local_install_scenarios.py` (19), `tests/js/offline_core_test.js` (17) | See "Testing". |

Small edits to existing code: `app.py` (wire-up at the end; `/api/scores/.../row` now also returns the row's `updated_at`; the score grid config carries each row's version `v`), `base.html` (loads the offline scripts instead of `online-only.js`, adds `sh-user` meta and a Sync Center link), `tests/v60`/`v65` (assertions that encoded the retired online-only policy). `online-only.js` is no longer loaded.

## How an offline change travels
1. Offline, a score save (`/api/scores/…/row`) or any ordinary POST form is stored in the device queue (encrypted), with a UUID **change id**, capture time and, for scores, the **base version** (the row's `updated_at` when last seen). A second edit of a still-queued row replaces the first and keeps the original base version.
2. When the school server answers `/api/sync/ping` again, the device refreshes its CSRF token and **replays each request against the real Flask route**, oldest first. Permissions, validation, the result-approval lock and the score audit trail therefore behave exactly as online.
3. `offline_sync.py` wraps the replay: a repeated change id is answered from `sync_changes` and never runs twice; a stale base version parks the change as a conflict; the server echoes `X-Sync-Ack: <change id>` and the device only treats a replay as done when it sees that header (a login page or a redirect is never mistaken for success).
4. Network errors / 5xx / 429 retry with back-off (up to 8 tries, then "Failed" with a Retry button). Rule failures (400/403/404/422/423) show the server's message as Failed and are kept until retried or discarded. Nothing is dropped silently.

## Conflict policy
* Score changed on the server since the device saw it: identical values → resolved automatically (audited); different values → **parked for an administrator** (sensitive academic data), who can *Keep server* or *Apply offline* (applied through the real score route as that administrator, with the usual audit row and lock checks).
* Attendance taken offline and replayed on a later school day is **parked** — the server-date-only attendance rule is not bypassed. Same-day attendance goes through the normal route.
* Every detection, auto-resolution and resolution writes to `audit_log`; every replay is in `sync_changes`.

## Security
* Cached pages carry `X-SH-User` (hash of user+school+tenant); the worker caches a page only if the tag equals the active user, and purges pages when the user changes or logs out. Queued changes are tagged with their owner and only replayed while that user is signed in. Logging out with unsynced changes asks first.
* Offline access expires `OFFLINE_WINDOW_DAYS` (default 7) after the last online check; the device then asks for a connection and sign-in.
* RBAC offline is inherited: pages were rendered by the server for that user's role, and every replay is re-authorised by the server.
* Queued payloads and files are AES-GCM encrypted with a non-extractable key in IndexedDB **where the browser supports WebCrypto (HTTPS or localhost)**; otherwise they are stored unencrypted and the Sync Center says so. Cached HTML (Cache Storage) is not encrypted — a browser limitation; the `/platform` Super Admin area is never cached.

## Local SQLite installation
`python run_local.py` (this computer) or `--lan`. Data lives in `school-data/` (school.db, uploads, backups/). A verified backup is taken at start-up and every 6 hours (`local_backup.py`: backup / list / restore / restore-files; restoring keeps the replaced database as `pre-restore-*.db`; damaged or foreign files are refused).

## Moving to PostgreSQL later
The change log (`sync_changes`), conflict table and `client_uuid`/`updated_at` row versions use only portable column types and `INSERT … ON CONFLICT`. The offline layer talks to Flask routes, not to SQLite, so swapping the database layer does not touch it.

## Known limits (be aware before relying on it)
* **No CBT module exists in v112**, so offline CBT (downloaded questions, timers, auto-submit) was not built; it needs the online CBT module first.
* **Fees:** v112 stores only the fee *summary* figures (`school_fee_summary`); there are no per-payment records to sync. Fee forms queue like any other form, but there is no financial conflict detection beyond duplicate protection.
* Row-level conflict detection exists for **scores** and **stale attendance**. Other queued forms (students, staff, classes, timetable, notifications…) get duplicate protection and the route's own validation, but last-write-wins.
* The score grid shows "saved" immediately when offline; the status pill and Sync Center show it as pending until acknowledged.
* **Two-way row-level sync between a local school computer and a central online server is not implemented.** Local installs are independent; browsers sync to whichever server they point at.
* Browsers offer service workers, install-as-app and encryption only on HTTPS or `localhost`; plain `http://192.168.x.x` gets none of them.
* Offline pages work only for screens opened while online at least once (the app pre-fetches the main menu pages once an hour).
* Queued file uploads are limited to 5 MB per change. File inputs on forms replay as multipart.

## Update: automatic offline preparation, header indicator, attendance sync fix
* **Offline preparation at sign-in.** On the first sign-in on a device, a short "Getting your school ready for offline use" screen appears while the service worker downloads the user's menu pages, the pages they link to (class lists, score entry, roll calls …) and the CSS/JS they need. Nothing has to be clicked. It refreshes quietly once an hour afterwards and again after the next sign-in following a logout. Links that look like actions (delete, approve, export, logout …) are never fetched. In the end-to-end test a teacher login cached 33 pages.
* **Header indicator** (`#shConn` in the top bar): green *Online*, red *Offline*; blue *Synchronizing n/m*, amber *Sync Failed*; with "· n pending", "· preparing offline n/m" and "· offline ready". Clicking it opens the Sync Center.
* **Attendance could not synchronize — cause and fix.** A replayed form follows the server's redirect, so the device never saw the server's confirmation and treated the save as unconfirmed; validation errors (flash + redirect) were also invisible. Replayed forms now get a JSON outcome: 200 on success, 422 with the route's own message when the form is rejected (e.g. "already recorded today"). Saving the roll call twice offline keeps one queued record.
* **Offline detection at submit time.** Before any queueable form is submitted, the page checks the school server answers; if not, the data is queued instead of being lost to a browser error page (this covers "Wi-Fi is up but the school server is down").
* New end-to-end browser test `tests/v113_offline_e2e.py` (27 checks): login → auto-preparation → server stopped → red indicator, cached pages open → attendance and a score saved offline → server restarted → synced, no duplicates.

Still true: pages are only available offline if they were reachable from the menu in the first two link levels; a page deeper than that opens offline only if it was visited before. Server-generated downloads (PDF/Excel exports, new report cards) need the server.

## Update 2: silent preparation, teachers resolve their own score conflicts
* **Silent preparation.** The "Getting your school ready for offline use" screen and the "preparing offline" text are gone. The pages are still downloaded in the background right after sign-in; nothing is shown (verified by the browser test: the screen never appears).
* **Why a teacher saw so many conflicts, and the fix.** When a teacher's score page was opened offline from the prepared cache, the device had no record of the version the row started from, so every offline edit of an existing score looked like it clashed with the server. The device now takes the starting version from the page it is showing (online: always; offline: only where it has none). A browser test edits an existing score offline from the prepared cache and confirms no conflict is raised. Genuine clashes (someone else really changed the score in between) are still caught.
* **Teachers resolve their own conflicts.** The Sync Center now has a "Scores to review" card for everyone: it lists, with student and subject names, the value on the server and the value typed offline. A teacher sees and resolves only their own entries; administrators see everyone's (and who entered each). Buttons: *Keep server*, *Use mine*, plus *Use mine for all* / *Keep server for all*. "Use mine" runs through the normal score route as that user, so the teacher-assignment check, the approved/locked-results rule, range checks and the audit trail all still apply (a locked class refuses it and the conflict stays open). Every resolution is audited.
* Not done: field-by-field merging (for example the teacher changed CA1 and someone else changed Exam). A conflict is per score row.

## Update 3 (V114 offline layer): several people per device, offline sign-in, one-time silent preparation
* **Per-person encryption.** Each person who signs in online on a device gets a random data key, stored only wrapped by a key derived from their password (PBKDF2, 250,000 rounds). While they are signed in the key is held as a non-extractable browser key; sign-out, idle lock (30 min offline) or removal deletes it. Queued changes (and uploaded files) and every cached page are encrypted with it. Where WebCrypto is missing (plain http on a LAN) nothing is encrypted and offline sign-in is refused.
* **Offline sign-in.** The service worker shows `/offline` (a sign-in form) when nobody is signed in and the server cannot be reached. The password is checked locally by trying to open the wrapped key. Identifiers accepted: whatever the person typed online (username / email / phone …, plus School ID if used) and their username. Neutral error for wrong or unknown users; 5 wrong tries lock that account for 30 s doubling up to 15 min. Offline access lasts `OFFLINE_WINDOW_DAYS` (7) from that person's last online verification.
* **Many people, one device.** One page cache per person (`sh-pages-v114-<user>`), one key per person, queue entries tagged with their owner and replayed only while that person is signed in. Signing out never deletes anything; "Remove from this device" (Sync Center) does.
* **Offline-signed-in people have no server session.** When the connection returns they are asked once for their password; the app signs them in to the server in the background and sends their waiting changes.
* **Already signed in online but locked** (e.g. upgraded from an earlier build): a one-time "turn on offline mode" password prompt, verified by `/api/sync/verify-password` (5 tries / 10 min per person).
* **Preparation is once per person per device** (flag `prepared:<user>` = version). It crawls three link levels (max 600 pages) plus CSS/JS/fonts, silently. Pages stay current as people browse online; "Refresh offline pages now" re-downloads on demand. A version bump re-prepares once.
* **Tests:** `tests/js/offline_core_test.js` (27), `tests/v113_offline_scenarios.py` (83), `tests/v113_local_install_scenarios.py` (19), `tests/v113_offline_e2e.py` (36, two people on one browser, real server stop/start).
* **Limits:** a password changed online starts a fresh key (anything still waiting from before shows Failed and must be re-entered); the password is held in sessionStorage for one page load at sign-in to set the key up; cached CSS/JS/fonts are not encrypted (they hold no school data); third-party CDN assets (React, Bootstrap, fonts) were not testable without internet in the sandbox; not tried on real phones/tablets.
