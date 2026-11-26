# V116 — One login page for online and offline use

## How it works
* **One page: `/login`.** The old separate offline sign-in screen is now only a fallback (used if the login page was never cached).
* **Connection detection** (`static/js/offline/unified-login.js`): browser online/offline events + a small ping to `/api/sync/ping` (every 8 s, on focus, and again before submit with one retry so a slow server is not mistaken for "offline"). The page shows Online / Offline states in `#loginConn` (screen-reader announced).
* **Online:** the form posts to the Flask `/login` exactly as before. Roles, permissions, rate-limits, school/subscription checks are the server's. The first online sign-in on a device enrols that person (see below).
* **Offline:** only people who already signed in on THIS device while online. The password is checked on the device by opening the encrypted key that was wrapped with it (PBKDF2, 250,000 rounds; offline-core.js). **The password itself is never stored**; the one-page-load stash used for enrolment is cleared after any offline attempt. 5 wrong tries lock that account on that device with a growing delay; offline access expires after `OFFLINE_WINDOW_DAYS` (default 7) since the last online check.
* **First-time offline sign-in on an unregistered device is refused:** if nobody is enrolled on the device the page says so and does not even try the password (also refused: first-time student sign-in with a Class Login Code, and devices without a secure context).
* **Service worker** keeps an *anonymous* copy of `/login` (fetched without cookies: no session, flash message or person's data) plus the static files it needs, and serves it when the server cannot be reached or nobody is signed in. A copy opened offline carries a stale CSRF token; a fresh one is fetched when the connection returns and before an online submit.
* After an offline sign-in the person lands on the page they asked for (or `/dashboard`). Offline-signed-in people are asked once for their password when the connection returns, so waiting changes can be sent (existing V114 behaviour).

## Fixes found while testing (please read)
1. **Sign-out race (pre-existing):** right after a first sign-in the service worker silently downloads ~100 pages. Pages requested with the old cookie that answered *after* `/logout` re-saved the old session, so the person could still be signed in. Signing out now aborts those downloads (`LOCK` message → `prepCtl.abort()`).
2. **My v115 mistake:** the per-person page cache name contained the worker version, so v115 would have discarded every device's offline pages on update. The name is now fixed (`PAGES_VERSION = 'v114'`), and `OFFLINE_VERSION` is `v116` so every person silently re-prepares once (recovers devices that already lost pages).

## Scope / limits (be aware)
* Offline sign-in covers **staff accounts** (admins, teachers, accountants, registrars – the `user_id` sessions that already had offline support). **Students and parents sign in online only**, as before: they have no offline enrolment and their pages are not pre-cached. The Super Admin `/platform` area stays online-only.
* Needs HTTPS (or localhost) for WebCrypto, service workers and install-as-app; on plain `http://192.168.x.x` the page says offline sign-in is unavailable.
* A device must have loaded `/login` online at least once (so the service worker can keep the copy) before it can show the page offline. A brand-new browser with no cached copy cannot open any page offline.
* A password changed online starts a fresh key on that device (anything still waiting from before must be re-entered).
* Android: works in Chrome / installed PWA. Not tested on a physical Android phone or iOS in this build.

## Tests
`tests/v116_scenarios.py` (18, wiring), `tests/v116_unified_login_e2e.py` (18, real browser: unregistered device refused offline → online sign-in as teacher/admin → offline sign-in on the same page with wrong/unknown people refused → stale token refreshed), `tests/v113_offline_e2e.py` updated to the unified page (36). All 53 scenario scripts + JS unit tests pass.
