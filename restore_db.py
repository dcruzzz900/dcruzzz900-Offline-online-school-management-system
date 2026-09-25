#!/usr/bin/env python3
"""Safely restore a verified SQLite backup.

Run during a maintenance window with the web process stopped:
  python restore_db.py --source /data/backups/school-YYYYMMDD-HHMMSS.db --confirm

The current database is backed up before replacement. The backup is restored
through SQLite's backup API and integrity-checked before an atomic replace.
"""
import argparse
import os
import sqlite3
import tempfile
from datetime import datetime


def integrity(path):
    conn = sqlite3.connect(path, timeout=60)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


ap = argparse.ArgumentParser()
ap.add_argument("--source", required=True)
ap.add_argument("--confirm", action="store_true")
args = ap.parse_args()

if not args.confirm:
    raise SystemExit("Refusing to restore without --confirm.")
if not os.path.isfile(args.source):
    raise SystemExit(f"Backup not found: {args.source}")

data_dir = os.environ.get("DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")
target = os.path.join(data_dir, "school.db")
os.makedirs(data_dir, exist_ok=True)

if integrity(args.source) != "ok":
    raise SystemExit("Source backup failed integrity_check; nothing was changed.")

if os.path.exists(target):
    # Make a rollback snapshot before touching the live database.
    from backup_db import make_backup
    rollback, _ = make_backup(os.path.join(data_dir, "backups"), keep=30)
    print(f"Rollback backup: {rollback}")

fd, temp = tempfile.mkstemp(prefix=".restore-", suffix=".db", dir=data_dir)
os.close(fd)
try:
    src = sqlite3.connect(args.source, timeout=60)
    dst = sqlite3.connect(temp, timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    if integrity(temp) != "ok":
        raise SystemExit("Restored temporary database failed integrity_check; live database was not changed.")
    os.replace(temp, target)
    print(f"Restore complete: {target}")
finally:
    if os.path.exists(temp):
        os.remove(temp)
