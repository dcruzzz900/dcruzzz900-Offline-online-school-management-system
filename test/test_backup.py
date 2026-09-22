import os
import sqlite3
import tempfile
from helpers import fresh_app, ROOT


def test_backup_is_a_verified_consistent_copy_and_old_ones_are_pruned():
    m, tmp = fresh_app()
    import sys
    sys.path.insert(0, ROOT)
    import backup_db
    dest = tempfile.mkdtemp()
    first, schools = backup_db.make_backup(dest, keep=2)
    assert schools == 1 and os.path.getsize(first) > 10000
    conn = sqlite3.connect(first)
    assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 3        # the demo school's pupils
    conn.close()
    import time
    for _ in range(3):
        time.sleep(1.1)
        backup_db.make_backup(dest, keep=2)
    assert len([f for f in os.listdir(dest) if f.endswith(".db")]) == 2            # only the newest two kept
