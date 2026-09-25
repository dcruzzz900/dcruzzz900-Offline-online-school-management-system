#!/usr/bin/env python3
"""Railway production entrypoint: validate the persistent volume, snapshot the
existing DB, then hand off to Gunicorn. It deliberately does not import app
before the backup, so migrations can never run before the pre-update snapshot.
"""
import os
import sqlite3
import subprocess
import sys
import time


def fail(message):
    print(f"[startup] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID") or os.environ.get("FLASK_ENV") == "production":
    data_dir = os.environ.get("DATA_DIR")
    if not data_dir:
        fail("DATA_DIR is required in production and must point to a Railway Volume.")
    if os.path.abspath(data_dir) != os.path.abspath("/data"):
        print(f"[startup] DATA_DIR={data_dir}; confirm this is the persistent Railway Volume.", file=sys.stderr)

    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "school.db")
    if os.path.exists(db_path):
        try:
            check = sqlite3.connect(db_path, timeout=30)
            verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
            check.close()
        except Exception as exc:
            fail(f"existing database could not be opened safely: {exc}")
        if verdict != "ok":
            fail(f"existing database failed integrity_check: {verdict}")

        # backup_db uses SQLite's online backup API, so the snapshot is
        # consistent even if the service is restarted while the DB is busy.
        from backup_db import make_backup
        target, schools = make_backup(os.path.join(data_dir, "backups"), keep=30)
        print(f"[startup] Pre-update backup: {target} ({schools} school(s))", flush=True)
    else:
        if os.environ.get("ALLOW_NEW_DATABASE") != "1":
            fail("school.db is missing. Refusing to create a fresh production database; verify the Railway Volume mount or explicitly initialize a new empty deployment with ALLOW_NEW_DATABASE=1.")

    if os.environ.get("SKIP_DEMO_SEED") != "1":
        fail("SKIP_DEMO_SEED=1 is required in production.")

    if len(os.environ.get("SECRET_KEY", "")) < 32:
        fail("SECRET_KEY must be set to a long random value (32+ characters).")

cmd = [
    "gunicorn", "app:app",
    "--workers", "1",
    "--threads", "8",
    "--timeout", "120",
    "--graceful-timeout", "30",
    "--keep-alive", "5",
    "--max-requests", "1000",
    "--max-requests-jitter", "100",
    "--bind", "0.0.0.0:" + os.environ.get("PORT", "8000"),
]
os.execvp(cmd[0], cmd)
