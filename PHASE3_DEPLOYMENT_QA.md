# Phase 3 — Deployment Readiness QA

## Completed in v19

- Production startup now defaults Flask debug mode to **off** (`FLASK_DEBUG=0`).
- Railway deployment guidance includes a post-deploy verification checklist.
- PythonAnywhere deployment guidance no longer instructs operators to use demo credentials.
- Production guidance explicitly covers `SECRET_KEY`, `SESSION_COOKIE_SECURE=1`, and `SKIP_DEMO_SEED=1`.
- Health check expectations are documented.
- SQLite single-worker and persistent-volume requirements remain explicit.

## Required before go-live

1. Install `requirements.txt` in the target environment.
2. Run `python -m pytest -q`.
3. Verify `/healthz` returns 200.
4. Create a fresh production database with `SKIP_DEMO_SEED=1`.
5. Run the migration suite against a copy of the live database.
6. Take a verified backup before deployment.
7. Test Admin → Teacher → Student → Parent workflows.
8. Test parent/teacher message authorization across two schools.
9. Test offline queue/replay after a real login session.
10. Perform a backup restore drill.
