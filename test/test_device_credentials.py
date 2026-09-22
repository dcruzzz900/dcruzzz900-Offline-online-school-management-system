"""Device credentials: ownership, hashing, expiry after weeks offline, and
renewal that keeps the device's identity."""
import datetime
from helpers import fresh_app, login, csrf, enroll, device_headers, new_device, push, change, bootstrap


def _db():
    import db
    return db.get_db()


def test_cannot_take_over_another_users_device_by_reusing_its_id():
    m, _ = fresh_app()
    import db
    conn = _db()
    conn.execute("UPDATE users SET role='sub_admin' WHERE username='aokafor'")
    conn.commit()
    conn.close()
    admin_dev, admin_cred = new_device(m, "admin", "admin123", "main admin's tablet")
    # a sub-admin (who can read the audit trail, which lists device ids) tries to re-enrol using the main admin's device id
    c = m.app.test_client()
    assert login(c, "aokafor", "teacher123").status_code == 302
    stolen = enroll(c, "sneaky", device_id=admin_cred["device_id"])
    assert stolen["device_id"] != admin_cred["device_id"]                     # the id was NOT reused
    assert stolen["user"]["user_id"] != admin_cred["user"]["user_id"]
    # the main admin's device secret still works; the sub-admin's new one acts as the sub-admin only
    assert admin_dev.get("/api/sync/bootstrap", headers=device_headers(admin_cred)).status_code == 200
    d2 = m.app.test_client()
    assert d2.get("/api/sync/audit", headers=device_headers(stolen)).status_code == 200     # sub-admin role
    conn = _db()
    row = conn.execute("SELECT user_id, school_id FROM device_credentials WHERE device_id=?", (admin_cred["device_id"],)).fetchone()
    assert row["user_id"] == admin_cred["user"]["user_id"]
    conn.close()


def test_device_secrets_use_fast_hash_but_legacy_scrypt_ones_still_verify():
    m, _ = fresh_app()
    dev, cred = new_device(m, "admin", "admin123")
    conn = _db()
    assert conn.execute("SELECT secret_hash FROM device_credentials WHERE device_id=?", (cred["device_id"],)).fetchone()[0].startswith("sha256$")
    from werkzeug.security import generate_password_hash
    conn.execute("UPDATE device_credentials SET secret_hash=? WHERE device_id=?", (generate_password_hash(cred["device_secret"]), cred["device_id"]))
    conn.commit()
    conn.close()
    assert dev.get("/api/sync/bootstrap", headers=device_headers(cred)).status_code == 200
    bad = dict(cred, device_secret="nope")
    assert dev.get("/api/sync/bootstrap", headers=device_headers(bad)).status_code == 401


def test_weeks_offline_credential_expires_with_a_reason_and_renewal_keeps_the_device_id():
    m, _ = fresh_app()
    dev, cred = new_device(m, "admin", "admin123", "tablet")
    conn = _db()
    past = (datetime.datetime.utcnow() - datetime.timedelta(days=2)).isoformat(timespec="seconds")
    conn.execute("UPDATE device_credentials SET expires_at=? WHERE device_id=?", (past, cred["device_id"]))
    conn.commit()
    conn.close()
    r = dev.get("/api/sync/bootstrap", headers=device_headers(cred))
    assert r.status_code == 401 and r.get_json()["status"] == "expired"
    assert dev.post("/api/offline/verify", json={"device_id": cred["device_id"], "device_secret": cred["device_secret"]}).get_json()["status"] == "expired"
    # back online the user logs in and the app renews the SAME device (new secret, same id)
    c = m.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    renewed = enroll(c, "tablet", device_id=cred["device_id"])
    assert renewed["device_id"] == cred["device_id"] and renewed["device_secret"] != cred["device_secret"]
    assert dev.get("/api/sync/bootstrap", headers=device_headers(renewed)).status_code == 200
    assert dev.get("/api/sync/bootstrap", headers=device_headers(cred)).status_code == 401      # the old secret is dead


def test_reasons_for_each_way_a_device_can_be_cut_off():
    m, _ = fresh_app()
    import db
    dev, cred = new_device(m, "aokafor", "teacher123")
    conn = _db()
    def reason():
        return dev.get("/api/sync/pull?since=2000-01-01T00:00:00", headers=device_headers(cred)).get_json()
    conn.execute("UPDATE schools SET is_suspended=1")
    conn.commit()
    assert reason()["status"] == "school_suspended"
    conn.execute("UPDATE schools SET is_suspended=0")
    conn.commit()
    conn.execute("UPDATE device_credentials SET revoked=1")
    conn.commit()
    assert reason()["status"] == "revoked"
    conn.close()


def test_password_reset_cuts_off_saved_devices_and_the_device_count_is_capped():
    m, _ = fresh_app()
    import db
    dev, cred = new_device(m, "aokafor", "teacher123", "phone")
    assert dev.get("/api/sync/bootstrap", headers=device_headers(cred)).status_code == 200
    conn = _db()
    tid = conn.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0]
    conn.close()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    admin.post(f"/admin/teachers/{tid}/reset_password", data={"csrf_token": csrf(admin)})
    r = dev.get("/api/sync/bootstrap", headers=device_headers(cred))
    assert r.status_code == 401 and r.get_json()["status"] == "revoked"
    # ...and the person renews the SAME device by logging in with the new password (the login page does this)
    conn = _db()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (__import__("werkzeug.security", fromlist=["x"]).generate_password_hash("Fresh-pass-9"), tid))
    conn.commit()
    conn.close()
    c = m.app.test_client()
    assert login(c, "aokafor", "Fresh-pass-9").status_code == 302
    renewed = enroll(c, "phone", device_id=cred["device_id"])
    assert renewed["device_id"] == cred["device_id"]
    assert dev.get("/api/sync/bootstrap", headers=device_headers(renewed)).status_code == 200

    # a person can't pile up unlimited live devices
    conn = _db()
    admin_id, school = conn.execute("SELECT id, school_id FROM users WHERE username='admin'").fetchone()
    for i in range(14):
        db.issue_device_credential(conn, school, admin_id, "admin", None, device_label=f"phone {i}")
    live = conn.execute("SELECT COUNT(*) FROM device_credentials WHERE user_id=? AND revoked=0", (admin_id,)).fetchone()[0]
    newest_ok = conn.execute("SELECT COUNT(*) FROM device_credentials WHERE user_id=? AND revoked=0 AND device_label='phone 13'", (admin_id,)).fetchone()[0]
    conn.close()
    assert live == db.MAX_DEVICES_PER_USER and newest_ok == 1
