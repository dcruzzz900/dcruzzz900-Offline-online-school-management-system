"""Upgrades: a fresh database, a database from the offline-sync build (v26),
and a database created by the earlier queue-based build (v25, which used the
same version numbers 24-25 for different migrations)."""
import os
import shutil
import sqlite3
import sys
import tempfile
import importlib
from helpers import ROOT

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_db(tmp):
    os.environ["DATA_DIR"] = tmp
    os.environ.pop("SKIP_DEMO_SEED", None)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    sys.modules.pop("db", None)
    return importlib.import_module("db")


def _assert_fully_upgraded(db, conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM schema_steps")}
    assert names == {n for n, _ in db.STEPS}, names
    cols = lambda t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
    assert {"ca3"} <= cols("scores") and {"ca3_max"} <= cols("grading_config")
    assert {"level", "arm"} <= cols("classes") and {"is_active"} <= cols("users")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"device_credentials", "change_audit", "sync_tombstones", "offline_sync_tokens"} <= tables
    gc = conn.execute("SELECT ca3_max, client_uuid, updated_at FROM grading_config").fetchone()
    assert gc["ca3_max"] == 0 and gc["client_uuid"] and gc["updated_at"]
    # tombstone triggers are live
    sid = conn.execute("SELECT id FROM schools LIMIT 1").fetchone()[0]
    n = conn.execute("SELECT COUNT(*) FROM sync_tombstones").fetchone()[0]
    conn.execute("INSERT INTO subjects (school_id, name) VALUES (?, 'zz-throwaway')", (sid,))
    conn.execute("DELETE FROM subjects WHERE name='zz-throwaway'")
    assert conn.execute("SELECT COUNT(*) FROM sync_tombstones").fetchone()[0] == n + 1
    conn.rollback()


def test_fresh_database():
    db = _load_db(tempfile.mkdtemp(prefix="srs_fresh_"))
    db.init_db()
    conn = db.get_db()
    _assert_fully_upgraded(db, conn)
    db.run_migrations(conn)     # second run is a no-op
    conn.close()


def test_upgrade_from_offline_sync_build_v26_keeps_data_and_defaults_ca3_off():
    db = _load_db(tempfile.mkdtemp(prefix="srs_mig_"))
    os.makedirs(db.INSTANCE_DIR, exist_ok=True)
    conn = db.get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    fns = list(db.MIGRATIONS) + [f for _, f in db.STEPS[:3]]        # 1..23 then offline_sync, deferred_actions, sync_triggers
    for i, fn in enumerate(fns, start=1):
        fn(conn)
        conn.execute("UPDATE schema_version SET version=?", (i,))
    conn.commit()
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 26
    db.seed(conn)
    sid = conn.execute("SELECT id FROM students").fetchone()[0]
    subj = conn.execute("SELECT id FROM subjects").fetchone()[0]
    term = conn.execute("SELECT id FROM terms").fetchone()[0]
    conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,12,13,50)", (sid, subj, term))
    conn.commit()
    conn.close()

    conn = db.get_db()
    db.run_migrations(conn)
    assert tuple(conn.execute("SELECT ca1, ca2, ca3, exam FROM scores").fetchone()) == (12, 13, 0, 50)
    _assert_fully_upgraded(db, conn)
    conn.close()


def test_upgrade_from_queue_build_v25_database():
    """A real database made by the earlier queue-based build's own code
    (tests/fixtures/queue_build_v25.db): version 25, with users.is_active and
    offline_sync_tokens but NONE of the sync-engine tables."""
    tmp = tempfile.mkdtemp(prefix="srs_qb_")
    db = _load_db(tmp)
    os.makedirs(db.INSTANCE_DIR, exist_ok=True)
    shutil.copy(os.path.join(HERE, "fixtures", "queue_build_v25.db"), db.DB_PATH)
    raw = sqlite3.connect(db.DB_PATH)
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 25
    assert not raw.execute("SELECT 1 FROM sqlite_master WHERE name='device_credentials'").fetchone()
    raw.close()

    conn = db.get_db()
    db.init_db()
    db.run_migrations(conn)
    _assert_fully_upgraded(db, conn)
    # the data the old build had is intact, including its deactivated teacher and its score
    assert conn.execute("SELECT is_active FROM users WHERE username='aokafor'").fetchone()[0] == 0
    assert tuple(conn.execute("SELECT ca1, ca2, ca3, exam FROM scores").fetchone()) == (14, 15, 0, 52)
    assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 3
    conn.close()

    # and the upgraded database really runs the whole app: log in, enrol a device, sync
    from helpers import login, enroll, device_headers
    for m in ("sync_api", "app"):
        sys.modules.pop(m, None)
    app_mod = importlib.import_module("app")
    app_mod.app.config["TESTING"] = True
    c = app_mod.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    cred = enroll(c)
    boot = app_mod.app.test_client().get("/api/sync/bootstrap", headers=device_headers(cred)).get_json()
    assert len(boot["entities"]["students"]) == 3 and len(boot["entities"]["scores"]) == 1


def test_skip_demo_seed_env():
    tmp = tempfile.mkdtemp(prefix="srs_noseed_")
    db = _load_db(tmp)
    os.environ["SKIP_DEMO_SEED"] = "1"
    try:
        db.init_db()
        conn = db.get_db()
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        conn.close()
    finally:
        os.environ.pop("SKIP_DEMO_SEED", None)
