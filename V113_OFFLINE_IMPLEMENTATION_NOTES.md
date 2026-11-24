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
