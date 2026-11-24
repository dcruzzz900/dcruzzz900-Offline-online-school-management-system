#!/usr/bin/env python3
"""Automatic local backups and recovery for a school running My School Hub on its own computer (SQLite).

    python local_backup.py backup                  # one verified snapshot now (also copies uploaded files)
    python local_backup.py list
    python local_backup.py restore school-20261124-101500.db     # STOP the server first
    python local_backup.py restore-files files-20261124-101500.zip

Snapshots use SQLite's online-backup call (safe while the app is running) and are integrity-checked before they are kept.
run_local.py starts BackupScheduler, so a backup is taken at start-up and then every few hours without anyone doing anything.
Restoring never discards the current database: it is first saved as pre-restore-<time>.db next to the other backups."""
import argparse
import datetime
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

FILE_DIRS = ("materials", "uploads", "logos", "documents")      # folders of uploaded files that live beside the database


def backup_dir():
    d = os.path.join(db.INSTANCE_DIR, "backups")
    os.makedirs(d, exist_ok=True)
    return d


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")


def verify(path):
    """True only if the file is a healthy SQLite database that really is a School Hub database."""
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
            return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schools'").fetchone() is not None
        finally:
            c.close()
    except sqlite3.Error:
        return False


def make_backup(keep=14, include_files=True, prefix="school"):
    """Snapshot the live database (+ uploaded files). Returns the path of the .db snapshot. Raises RuntimeError if it fails its check."""
    if not os.path.exists(db.DB_PATH):
        raise RuntimeError("There is no database to back up yet.")
    stamp = _stamp()
    target = os.path.join(backup_dir(), f"{prefix}-{stamp}.db")
    src = sqlite3.connect(db.DB_PATH, timeout=60)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    if not verify(target):
        os.remove(target)
        raise RuntimeError("The backup failed its integrity check and was discarded.")
    if include_files:
        folders = [(n, os.path.join(db.INSTANCE_DIR, n)) for n in FILE_DIRS if os.path.isdir(os.path.join(db.INSTANCE_DIR, n))]
        if folders:
            with zipfile.ZipFile(os.path.join(backup_dir(), f"files-{stamp}.zip"), "w", zipfile.ZIP_DEFLATED) as z:
                for name, root in folders:
                    for base, _dirs, files in os.walk(root):
                        for f in files:
                            full = os.path.join(base, f)
                            z.write(full, os.path.relpath(full, db.INSTANCE_DIR))
    _prune(keep)
    return target


def _prune(keep):
    if keep <= 0:
        return
    for pattern_prefix, suffix in (("school-", ".db"), ("files-", ".zip")):
        names = sorted(f for f in os.listdir(backup_dir()) if f.startswith(pattern_prefix) and f.endswith(suffix))
        for old in names[:-keep]:
            os.remove(os.path.join(backup_dir(), old))


def list_backups():
    out = []
    for f in sorted(os.listdir(backup_dir()), reverse=True):
        if f.endswith((".db", ".zip")):
            p = os.path.join(backup_dir(), f)
            out.append({"name": f, "bytes": os.path.getsize(p), "modified": datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds")})
    return out


def restore_backup(name):
    """Replace the live database with a verified backup. The server must be stopped. Returns the path of the safety copy."""
    path = name if os.path.isabs(name) else os.path.join(backup_dir(), name)
    if not os.path.exists(path):
        raise RuntimeError(f"Backup not found: {name}")
    if not verify(path):
        raise RuntimeError("That backup is damaged or is not a My School Hub database. Nothing was changed.")
    safety = None
    if os.path.exists(db.DB_PATH):
        safety = os.path.join(backup_dir(), f"pre-restore-{_stamp()}.db")
        src = sqlite3.connect(db.DB_PATH, timeout=60)
        try:
            dst = sqlite3.connect(safety)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    tmp = db.DB_PATH + ".restoring"
    shutil.copyfile(path, tmp)
    if not verify(tmp):
        os.remove(tmp)
        raise RuntimeError("The copy failed its check. Nothing was changed.")
    for ext in ("-wal", "-shm"):
        if os.path.exists(db.DB_PATH + ext):
            os.remove(db.DB_PATH + ext)
    os.replace(tmp, db.DB_PATH)
    return safety


def restore_files(name):
    path = name if os.path.isabs(name) else os.path.join(backup_dir(), name)
    with zipfile.ZipFile(path) as z:
        root = os.path.realpath(db.INSTANCE_DIR)
        for m in z.namelist():
            if not os.path.realpath(os.path.join(root, m)).startswith(root + os.sep):
                raise RuntimeError("Unsafe path inside the files backup; nothing was restored.")
        z.extractall(root)


class BackupScheduler:
    """Daemon thread: a backup at start-up (if the newest is older than the interval) and then every `hours` hours."""
    def __init__(self, hours=6, keep=14, log=print):
        self.hours, self.keep, self.log = hours, keep, log
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="sh-backup", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self._stop.set()

    def due(self):
        dbs = [f for f in os.listdir(backup_dir()) if f.startswith("school-") and f.endswith(".db")]
        if not dbs:
            return True
        newest = max(os.path.getmtime(os.path.join(backup_dir(), f)) for f in dbs)
        return (datetime.datetime.now().timestamp() - newest) >= self.hours * 3600

    def run_once(self):
        try:
            if os.path.exists(db.DB_PATH) and self.due():
                self.log("Backup saved:", make_backup(keep=self.keep))
                return True
        except Exception as exc:       # a failed backup must never stop the school from working
            self.log("Backup problem:", exc)
        return False

    def _run(self):
        self.run_once()
        while not self._stop.wait(self.hours * 3600 / 4):
            self.run_once()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup"); b.add_argument("--keep", type=int, default=14); b.add_argument("--no-files", action="store_true")
    sub.add_parser("list")
    r = sub.add_parser("restore"); r.add_argument("name")
    f = sub.add_parser("restore-files"); f.add_argument("name")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "backup":
            print("Saved", make_backup(keep=a.keep, include_files=not a.no_files))
        elif a.cmd == "list":
            for x in list_backups():
                print(f"{x['modified']}  {x['bytes']:>12,}  {x['name']}")
        elif a.cmd == "restore":
            safety = restore_backup(a.name)
            print("Restored." + (f" The previous database was kept as {safety}" if safety else ""))
        elif a.cmd == "restore-files":
            restore_files(a.name); print("Files restored.")
    except RuntimeError as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
