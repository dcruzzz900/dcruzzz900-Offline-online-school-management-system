# Scaling to 1,000+ schools / 1,000+ simultaneous users (V102)

## What was measured (tests/load/, 1,000 schools, 31,000 students, one 1-vCPU sandbox that also ran the load generator)
| Operation (no contention) | Cost |
|---|---|
| Open a student's result page | ~82 ms CPU |
| Dashboard | ~9 ms |
| Save ratings + comment (a DB write) | ~14 ms net (96 ms incl. loading the page first) |
| Login (password check, deliberately slow) | ~360-400 ms CPU |

* Steady state is CPU-bound: ~12 result-page requests/second per core, as the 82 ms predicts.
* 4 server processes sharing one SQLite database, 60% writes, 80 users: **0 errors, 0 "database is locked", integrity_check ok.**
  So several workers on one machine are safe; the database is not what limits you yet. CPU is.
* The old config (1 worker x 8 threads) is therefore the bottleneck: ~12-15 requests/second for the whole country.

## Estimate for 1,000 simultaneous users (NOT measured - extrapolated from the per-core costs above)
* Typical mix (60% result pages, 25% dashboard, 15% saves) ~ 65 ms/request -> ~15 requests/s per core.
* 1,000 active users each making a request every ~10 s = ~100 requests/s -> about 7-8 cores.
* Morning login burst: 1,000 logins x ~0.4 s = ~400 CPU-seconds -> ~50 s on 8 cores. Do not weaken the password hash;
  add cores instead.
* Suggested start: one machine with 8 vCPU, `WEB_CONCURRENCY=8` (gunicorn workers; each has 8 threads), SSD volume,
  `RATE_LIMIT_DISABLED` unset. Re-run `tests/load/loadtest.py` on that machine to get real numbers.

## Changed in V102
* Login limiter was 10 attempts / 5 min **per IP** - a whole school behind one Wi-Fi/NAT IP (or one mobile gateway)
  was locked out after ten logins. Now: 10 / 5 min per IP **and username** (guessing one account is still blocked) plus a
  600 / 5 min ceiling per IP. (The counter is per worker process, so with N workers the effective caps are up to N x.)
* Procfile / railway.json: `--workers ${WEB_CONCURRENCY:-4}` (was fixed at 1), `--max-requests 2000` recycling.
  Safe because: migrations are already serialized across workers by a file lock, there are no background threads,
  and the only per-process state is the rate-limit counter.
* tests/load/seed_schools.py + loadtest.py: repeatable benchmark (N schools, ramped users, p50/p95/p99, errors).

## Honest limits / next phase (not done here)
* SQLite is a single machine: you cannot spread across servers, and one slow disk affects everyone. When you outgrow one
  machine, or need zero-downtime failover, move to **PostgreSQL** (+ Redis for the rate limiter/sessions, a job queue for
  bulk PDFs). That is a large change (~1,650 SQL calls, ~180 SQLite-specific constructs) that must be developed and tested
  against a real PostgreSQL server, which was not available in this build environment - so it was deliberately not attempted blind.
* Chromium PDF generation is ~1-2 s CPU each; bulk class downloads should move to a background queue at this scale.
* Back up the database file regularly (volume snapshots or Litestream) - it is now the whole business.
