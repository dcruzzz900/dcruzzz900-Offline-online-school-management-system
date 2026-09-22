import json
from helpers import (fresh_app, login, enroll, device_headers, make_school, new_device,
                     push, bootstrap, pull, change)


def _ctx():
    m, _ = fresh_app()
    import db
    conn = db.get_db()
    ids = dict(
        term=conn.execute("SELECT id FROM terms").fetchone()[0],
        cls=conn.execute("SELECT id FROM classes WHERE name='JSS1A'").fetchone()[0],
        subj=conn.execute("SELECT id FROM subjects ORDER BY id").fetchone()[0],
        student=conn.execute("SELECT id FROM students ORDER BY id").fetchone()[0],
        student2=conn.execute("SELECT id FROM students ORDER BY id LIMIT 1 OFFSET 1").fetchone()[0],
    )
    conn.close()
    return m, ids


def _score(ids, **kw):
    d = dict(student_id=ids["student"], subject_id=ids["subj"], term_id=ids["term"], ca1=10, ca2=10, ca3=0, exam=40)
    d.update(kw)
    return d


# ---------------------------------------------------------------- security

def test_credentials_never_sent_to_devices():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    ents = bootstrap(dev, cred)["entities"]
    for row in ents["users"]:
        for k in ("password_hash", "security_answer_hash", "security_question"):
            assert k not in row, k
    for row in ents["students"]:
        assert "password_hash" not in row and "username" not in row


def test_bootstrap_includes_school_profile_without_secrets():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    school = bootstrap(dev, cred)["school"]
    assert school["name"] == "My School"
    assert not any(k.startswith("smtp") for k in school)


def test_demoted_user_loses_access_on_existing_devices():
    m, ids = _ctx()
    import db
    conn = db.get_db()
    conn.execute("UPDATE users SET role='sub_admin' WHERE username='aokafor'")
    conn.commit()
    dev, cred = new_device(m, "aokafor", "teacher123")
    # while sub_admin the device can read staff
    assert "users" in bootstrap(dev, cred)["entities"]
    conn.execute("UPDATE users SET role='teacher' WHERE username='aokafor'")
    conn.commit()
    conn.close()
    # same device, no re-enrolment: must now be treated as a plain teacher
    assert "users" not in bootstrap(dev, cred)["entities"]


def test_cross_school_write_rejected_and_school_b_invisible():
    m, ids = _ctx()
    b = make_school(m)
    dev, cred = new_device(m, "admin", "admin123")
    # School A admin tries to write a score for School B's student
    res = push(dev, cred, [change("scores", dict(student_id=b["student_id"], subject_id=b["subject_id"],
                                                 term_id=b["term_id"], ca1=5, ca2=5, exam=5))])
    assert res[0]["status"] == "error" and "cross-school" in res[0]["message"]
    # ...and tries to re-point an existing A score at B's student (update path)
    ok = push(dev, cred, [change("scores", _score(ids), client_uuid="s-1")])
    assert ok[0]["status"] == "synced"
    bad = push(dev, cred, [change("scores", _score(ids, student_id=b["student_id"]), client_uuid="s-1",
                                  base_updated_at=ok[0]["updated_at"])])
    assert bad[0]["status"] == "error"
    # a foreign subject/term on A's own student is rejected too
    res = push(dev, cred, [change("scores", _score(ids, subject_id=b["subject_id"]))])
    assert res[0]["status"] == "error" and "cross-school" in res[0]["message"]
    # nothing from B is ever pulled by A
    ents = bootstrap(dev, cred)["entities"]
    assert all(r["admission_no"] != "B001" for r in ents["students"])
    assert all(r["name"] != "SS1A" for r in ents["classes"])
    assert all(r["name"] != "Physics" for r in ents["subjects"])


def test_sub_admin_cannot_modify_main_admin_account():
    m, ids = _ctx()
    import db
    conn = db.get_db()
    conn.execute("UPDATE users SET role='sub_admin' WHERE username='aokafor'")
    conn.commit()
    admin_uuid = conn.execute("SELECT client_uuid FROM users WHERE username='admin'").fetchone()[0]
    admin_updated = conn.execute("SELECT updated_at FROM users WHERE username='admin'").fetchone()[0]
    conn.close()
    dev, cred = new_device(m, "aokafor", "teacher123")
    res = push(dev, cred, [change("users", dict(name="Hacked", username="admin", role="admin", password="owned123"),
                                  client_uuid=admin_uuid, base_updated_at=admin_updated)])
    assert res[0]["status"] == "error"
    conn = db.get_db()
    row = conn.execute("SELECT name FROM users WHERE username='admin'").fetchone()
    conn.close()
    assert row["name"] == "Administrator"
    # and the main admin can't be turned into a teacher by an admin-role push either
    dev2, cred2 = new_device(m, "admin", "admin123")
    res = push(dev2, cred2, [change("users", dict(name="Administrator", username="admin", role="teacher"),
                                    client_uuid=admin_uuid, base_updated_at=admin_updated)])
    conn = db.get_db()
    assert conn.execute("SELECT role FROM users WHERE username='admin'").fetchone()["role"] == "admin"
    conn.close()


def test_deleting_via_sync_is_refused():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    ents = bootstrap(dev, cred)["entities"]
    st = ents["students"][0]
    res = push(dev, cred, [change("students", {}, client_uuid=st["client_uuid"], op="delete",
                                  base_updated_at=st["updated_at"])])
    assert res[0]["status"] == "error"
    import db
    conn = db.get_db()
    assert conn.execute("SELECT is_deleted FROM students WHERE id=?", (st["id"],)).fetchone()[0] == 0
    conn.close()


# ------------------------------------------------------------ score validation & CA3

def test_score_limits_and_ca3_switch():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    r = push(dev, cred, [change("scores", _score(ids, ca1=500))])
    assert r[0]["status"] == "error" and "maximum" in r[0]["message"]
    r = push(dev, cred, [change("scores", _score(ids, ca1=-1))])
    assert r[0]["status"] == "error"
    r = push(dev, cred, [change("scores", _score(ids, ca1="abc"))])
    assert r[0]["status"] == "error"
    # CA3 is refused while the school hasn't enabled it...
    r = push(dev, cred, [change("scores", _score(ids, ca3=5))])
    assert r[0]["status"] == "error" and "CA3" in r[0]["message"]
    import db
    conn = db.get_db()
    conn.execute("UPDATE grading_config SET ca1_max=15, ca2_max=15, ca3_max=10, exam_max=60")
    conn.commit()
    conn.close()
    # ...and accepted, within its own max, once enabled
    r = push(dev, cred, [change("scores", _score(ids, ca1=15, ca2=14, ca3=10, exam=55))])
    assert r[0]["status"] == "synced"
    r = push(dev, cred, [change("scores", _score(ids, student_id=ids["student2"], ca3=11))])
    assert r[0]["status"] == "error"


def test_grading_settings_reach_devices_read_only():
    m, ids = _ctx()
    dev, cred = new_device(m, "aokafor", "teacher123")
    ents = bootstrap(dev, cred)["entities"]
    assert len(ents["grading_config"]) == 1 and len(ents["grade_scale"]) >= 5
    g = ents["grading_config"][0]
    res = push(dev, cred, [change("grading_config", dict(ca1_max=100), client_uuid=g["client_uuid"],
                                  base_updated_at=g["updated_at"])])
    assert res[0]["status"] == "error"


# ---------------------------------------------------------------- conflict rules

def test_different_fields_merge_same_field_conflicts():
    m, ids = _ctx()
    devA, credA = new_device(m, "admin", "admin123", "A")
    devB, credB = new_device(m, "admin", "admin123", "B")
    first = push(devA, credA, [change("scores", _score(ids, ca1=10, ca2=10, exam=40), client_uuid="cell")])
    assert first[0]["status"] == "synced"
    base = first[0]["updated_at"]
    base_vals = _score(ids, ca1=10, ca2=10, exam=40)
    # Device A (offline) corrects CA1; Device B (offline) corrects the exam. Both start from `base`.
    a = push(devA, credA, [change("scores", _score(ids, ca1=12, ca2=10, exam=40), client_uuid="cell",
                                  base_updated_at=base, base_data=base_vals)])
    assert a[0]["status"] == "synced" and a[0]["outcome"] == "applied"
    b = push(devB, credB, [change("scores", _score(ids, ca1=10, ca2=10, exam=55), client_uuid="cell",
                                  base_updated_at=base, base_data=base_vals)])
    assert b[0]["status"] == "synced" and b[0]["outcome"] == "merged", b
    sd = b[0]["server_data"]
    assert sd["ca1"] == 12 and sd["exam"] == 55          # both people's work survived
    # Same field, different values -> conflict, nothing overwritten
    base2 = b[0]["updated_at"]
    v2 = {k: sd[k] for k in ("student_id", "subject_id", "term_id", "ca1", "ca2", "ca3", "exam")}
    x = push(devA, credA, [change("scores", _score(ids, ca1=14, ca2=10, exam=55), client_uuid="cell",
                                  base_updated_at=base2, base_data=v2)])
    assert x[0]["status"] == "synced"
    y = push(devB, credB, [change("scores", _score(ids, ca1=13, ca2=10, exam=55), client_uuid="cell",
                                  base_updated_at=base2, base_data=v2)])
    assert y[0]["status"] == "conflict" and y[0]["conflicting_fields"] == ["ca1"]
    import db
    conn = db.get_db()
    assert conn.execute("SELECT ca1 FROM scores WHERE client_uuid='cell'").fetchone()[0] == 14  # not overwritten
    assert conn.execute("SELECT COUNT(*) FROM sync_conflicts WHERE resolved=0").fetchone()[0] == 1
    conn.close()


def test_two_devices_create_same_score_cell_offline():
    m, ids = _ctx()
    devA, credA = new_device(m, "admin", "admin123", "A")
    devB, credB = new_device(m, "admin", "admin123", "B")
    a = push(devA, credA, [change("scores", _score(ids, ca1=15, ca2=0, exam=0), client_uuid="uuid-A")])
    assert a[0]["status"] == "synced"
    # B never saw A's row and entered only the exam mark for the same cell, under its OWN uuid
    b = push(devB, credB, [change("scores", _score(ids, ca1=0, ca2=0, exam=50), client_uuid="uuid-B")])
    assert b[0]["status"] == "synced" and b[0]["outcome"] == "merged"
    assert b[0]["canonical_client_uuid"] == "uuid-A"
    assert b[0]["server_data"]["ca1"] == 15 and b[0]["server_data"]["exam"] == 50
    import db
    conn = db.get_db()
    assert conn.execute("SELECT COUNT(*) FROM scores WHERE student_id=?", (ids["student"],)).fetchone()[0] == 1
    conn.close()
    # both fill the SAME field differently -> a real conflict, not a constraint error
    c = push(devB, credB, [change("scores", _score(ids, ca1=9, exam=0), client_uuid="uuid-C")])
    assert c[0]["status"] == "conflict" and "ca1" in c[0]["conflicting_fields"]


def test_attendance_latest_wins_with_audit_and_clock_clamp():
    m, ids = _ctx()
    devA, credA = new_device(m, "admin", "admin123", "A")
    devB, credB = new_device(m, "admin", "admin123", "B")
    att = dict(student_id=ids["student"], class_id=ids["cls"], term_id=ids["term"], date="2026-09-14", status="present")
    a = push(devA, credA, [change("attendance_records", att, client_uuid="att-1", client_ts="2026-09-14T08:00:00Z")])
    base = a[0]["updated_at"]
    # A later, real edit from device A
    a2 = push(devA, credA, [change("attendance_records", {**att, "status": "absent"}, client_uuid="att-1",
                                   base_updated_at=base, client_ts="2026-09-14T09:00:00Z")])
    assert a2[0]["status"] == "synced"
    # Device B edited from the older base, and its timestamp is EARLIER than the server's edit -> loses, but audited
    import datetime
    old_ts = "2000-01-01T00:00:00Z"
    b = push(devB, credB, [change("attendance_records", {**att, "status": "present"}, client_uuid="att-1",
                                  base_updated_at=base, client_ts=old_ts)])
    assert b[0]["status"] == "synced" and b[0]["outcome"] == "latest_wins"
    assert b[0]["server_data"]["status"] == "absent"
    # A phone whose clock claims 2099 must not win forever: clamped to arrival time
    far = "2099-01-01T00:00:00Z"
    cur = b[0]["server_data"]["updated_at"]
    c = push(devB, credB, [change("attendance_records", {**att, "status": "present"}, client_uuid="att-1",
                                  base_updated_at=base, client_ts=far)])
    assert c[0]["status"] == "synced"   # arrival time >= server's last edit, so it wins legitimately
    import db
    conn = db.get_db()
    outcomes = [r["outcome"] for r in conn.execute("SELECT outcome FROM change_audit WHERE client_uuid='att-1' ORDER BY id")]
    assert "latest_wins" in outcomes and len(outcomes) >= 4
    conn.close()


def test_retry_with_same_change_id_is_idempotent_and_history_kept():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    ch = change("scores", _score(ids, ca1=11), client_uuid="idem")
    r1 = push(dev, cred, [ch])
    r2 = push(dev, cred, [ch])
    assert r1[0]["status"] == r2[0]["status"] == "synced" and r2[0].get("duplicate")
    import db
    conn = db.get_db()
    assert conn.execute("SELECT COUNT(*) FROM scores WHERE client_uuid='idem'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM change_audit WHERE change_id=?", (ch["change_id"],)).fetchone()[0] == 1
    # edit history is kept in score_history for synced edits too
    e = push(dev, cred, [change("scores", _score(ids, ca1=13), client_uuid="idem", base_updated_at=r1[0]["updated_at"],
                                base_data=_score(ids, ca1=11))])
    assert e[0]["status"] == "synced"
    h = conn.execute("SELECT old_ca1, new_ca1, source, device_id FROM score_history ORDER BY id").fetchall()
    assert [(x["old_ca1"], x["new_ca1"], x["source"]) for x in h] == [(None, 11, "offline-sync"), (11, 13, "offline-sync")]
    assert h[0]["device_id"] == cred["device_id"]
    conn.close()


def test_edit_of_record_deleted_online_is_a_conflict_not_a_resurrection():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    r = push(dev, cred, [change("scores", _score(ids), client_uuid="ghost")])
    import db
    conn = db.get_db()
    conn.execute("UPDATE scores SET is_deleted=1 WHERE client_uuid='ghost'")
    conn.commit()
    conn.close()
    e = push(dev, cred, [change("scores", _score(ids, ca1=19), client_uuid="ghost", base_updated_at=r[0]["updated_at"])])
    assert e[0]["status"] == "conflict"


def test_unique_clash_surfaces_as_conflict():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    r = push(dev, cred, [change("subjects", dict(name="Mathematics"))])   # already exists
    assert r[0]["status"] == "conflict"


# ------------------------------------------------------- deletes, tombstones, audit

def test_online_hard_deletes_reach_devices_scoped_to_their_school():
    m, ids = _ctx()
    b = make_school(m)
    devA, credA = new_device(m, "admin", "admin123", "A")
    devB, credB = new_device(m, *b["admin"], "B")
    boot = bootstrap(devA, credA)
    stamp = boot["generated_at"]
    victim = boot["entities"]["subjects"][0]
    import db
    conn = db.get_db()
    conn.execute("DELETE FROM class_subjects WHERE subject_id=?", (victim["id"],))
    conn.execute("DELETE FROM subjects WHERE id=?", (victim["id"],))
    conn.commit()
    bstudent = conn.execute("SELECT client_uuid FROM students WHERE id=?", (b["student_id"],)).fetchone()[0]
    conn.execute("DELETE FROM students WHERE id=?", (b["student_id"],))
    conn.commit()
    conn.close()
    got = pull(devA, credA, "1970-01-01T00:00:00")["deleted"]
    assert {"entity": "subjects", "client_uuid": victim["client_uuid"]} in [
        {"entity": d["entity"], "client_uuid": d["client_uuid"]} for d in got]
    assert all(d["client_uuid"] != bstudent for d in got)            # B's deletion never reaches A
    gotb = pull(devB, credB, "1970-01-01T00:00:00")["deleted"]
    assert any(d["client_uuid"] == bstudent for d in gotb)
    assert all(d["client_uuid"] != victim["client_uuid"] for d in gotb)


def test_audit_endpoint_admin_only_and_school_scoped():
    m, ids = _ctx()
    b = make_school(m)
    devA, credA = new_device(m, "admin", "admin123")
    devT, credT = new_device(m, "aokafor", "teacher123")
    devB, credB = new_device(m, *b["admin"])
    push(devA, credA, [change("scores", _score(ids), client_uuid="aud-1")])
    r = devA.get("/api/sync/audit", headers=device_headers(credA)).get_json()["entries"]
    assert any(e["client_uuid"] == "aud-1" and e["device_id"] == credA["device_id"] for e in r)
    assert devT.get("/api/sync/audit", headers=device_headers(credT)).status_code == 403
    rb = devB.get("/api/sync/audit", headers=device_headers(credB)).get_json()["entries"]
    assert all(e["client_uuid"] != "aud-1" for e in rb)


def test_audit_never_stores_passwords():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    r = push(dev, cred, [change("users", dict(name="New T", username="newt", password="s3cret-pw", role="teacher"))])
    assert r[0]["status"] == "synced"
    import db
    conn = db.get_db()
    blob = " ".join(str(dict(x)) for x in conn.execute("SELECT * FROM change_audit"))
    assert "s3cret-pw" not in blob
    conn.close()


def test_synced_attendance_updates_report_card_days():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    base = dict(student_id=ids["student"], class_id=ids["cls"], term_id=ids["term"], status="present")
    rs = push(dev, cred, [change("attendance_records", {**base, "date": f"2026-09-{d:02d}"}) for d in (14, 15, 16)]
              + [change("attendance_records", {**base, "date": "2026-09-17", "status": "absent"})])
    assert all(r["status"] == "synced" for r in rs)
    import db
    conn = db.get_db()
    r = conn.execute("SELECT days_present, days_absent, days_school_opened FROM student_term_info WHERE student_id=?",
                     (ids["student"],)).fetchone()
    assert tuple(r) == (3, 1, 4)
    conn.close()


def test_enrollments_are_readable_reference_data():
    m, ids = _ctx()
    dev, cred = new_device(m, "aokafor", "teacher123")
    ents = bootstrap(dev, cred)["entities"]
    assert len(ents["enrollments"]) == 3


def test_offline_registered_student_gets_session_enrollment():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    r = push(dev, cred, [change("students", dict(admission_no="777", first_name="New", last_name="Kid", gender="M",
                                                 class_id=ids["cls"]), client_uuid="stu-new")])
    assert r[0]["status"] == "synced"
    import db
    conn = db.get_db()
    n = conn.execute("SELECT COUNT(*) FROM enrollments WHERE student_id=?", (r[0]["server_id"],)).fetchone()[0]
    conn.close()
    assert n == 1


def test_read_scope_matches_online_result_access():
    m, ids = _ctx()
    import db
    conn = db.get_db()
    # a second class + student + score that Mrs Okafor has nothing to do with
    conn.execute("INSERT INTO classes (school_id, name) SELECT school_id, 'JSS2A' FROM classes LIMIT 1")
    c2 = conn.execute("SELECT id FROM classes WHERE name='JSS2A'").fetchone()[0]
    conn.execute("INSERT INTO students (admission_no, first_name, last_name, gender, class_id) VALUES ('200','Other','Kid','F',?)", (c2,))
    s2 = conn.execute("SELECT id FROM students WHERE admission_no='200'").fetchone()[0]
    conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,5,5,5)", (s2, ids["subj"], ids["term"]))
    # she is form teacher of JSS1A but teaches NO subject there
    conn.execute("DELETE FROM class_subjects")
    conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,9,9,9)",
                 (ids["student"], ids["subj"], ids["term"]))
    conn.commit()
    dev, cred = new_device(m, "aokafor", "teacher123")
    ents = bootstrap(dev, cred)["entities"]
    assert {r["student_id"] for r in ents["scores"]} == {ids["student"]}      # her form class, not JSS2A
    assert {r["admission_no"] for r in ents["students"]} == {"001", "002", "003"}
    # promote her to a full-access position: can now READ every class (as the online result pages allow)
    conn.execute("UPDATE users SET position='principal' WHERE username='aokafor'")
    conn.commit()
    ents = bootstrap(dev, cred)["entities"]
    assert {r["student_id"] for r in ents["scores"]} == {ids["student"], s2}
    # ...but still can't WRITE outside her own classes
    r = push(dev, cred, [change("scores", dict(student_id=s2, subject_id=ids["subj"], term_id=ids["term"], ca1=1, ca2=1, exam=1))])
    assert r[0]["status"] == "error"
    conn.close()


def test_client_ids_must_be_boring():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    r = push(dev, cred, [change("scores", _score(ids), client_uuid='"><img src=x onerror=alert(1)>')])
    assert r[0]["status"] == "error"


def test_healthz_is_public():
    m, _ = fresh_app()
    r = m.app.test_client().get("/healthz")
    assert r.status_code == 200 and r.get_json()["status"] == "ok"


def test_password_hashed_on_the_device_is_accepted_and_works_for_login():
    import hashlib
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    salt = "Qw3rTy9uIoPa"
    digest = hashlib.pbkdf2_hmac("sha256", b"Their-Own-Pass1", salt.encode(), 600000).hex()
    r = push(dev, cred, [change("users", dict(name="Mr Device", username="mrdevice", role="teacher",
                                             password_hash=f"pbkdf2:sha256:600000${salt}${digest}"))])
    assert r[0]["status"] == "synced", r
    c = m.app.test_client()
    from helpers import login
    assert login(c, "mrdevice", "Their-Own-Pass1").status_code == 302      # logs in with the real password
    c2 = m.app.test_client()
    assert login(c2, "mrdevice", "wrong").status_code != 302


def test_weak_or_malformed_client_hashes_are_refused():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    good_tail = "$Qw3rTy9uIoPa$" + "a" * 64
    for bad in ("pbkdf2:sha256:1" + good_tail,               # 1 iteration: instantly crackable
                "pbkdf2:sha256:99999999" + good_tail,        # would make logins a CPU sink
                "md5$abc$def", "plaintext-password", "pbkdf2:sha256:600000$x$y"):
        r = push(dev, cred, [change("users", dict(name="X", username="x" + str(abs(hash(bad)) % 9999), role="teacher", password_hash=bad))])
        assert r[0]["status"] == "error", bad


def test_staff_edit_and_password_reset_rules():
    import hashlib
    m, ids = _ctx()
    import db
    conn = db.get_db()
    conn.execute("INSERT INTO users (school_id, name, username, password_hash, role) "
                 "SELECT school_id, 'Second Sub', 'secondsub', password_hash, 'sub_admin' FROM users WHERE username='admin'")
    conn.execute("UPDATE users SET role='sub_admin' WHERE username='aokafor'")
    conn.commit()
    rows = {r["username"]: dict(r) for r in conn.execute("SELECT * FROM users")}
    conn.close()
    salt = "Zx9Yw8Vu7Ts6"
    def hashed(pw):
        return f"pbkdf2:sha256:600000${salt}${hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 600000).hex()}"
    # main admin resets a sub-admin's password from a device: allowed
    dev, cred = new_device(m, "admin", "admin123")
    r = push(dev, cred, [change("users", dict(name="Second Sub", username="secondsub", role="sub_admin", password_hash=hashed("NewPass-77")),
                                client_uuid=rows["secondsub"]["client_uuid"], base_updated_at=rows["secondsub"]["updated_at"])])
    assert r[0]["status"] == "synced", r
    from helpers import login
    assert login(m.app.test_client(), "secondsub", "NewPass-77").status_code == 302
    # a sub-admin may NOT reset another sub-admin's, nor the main admin's password
    subdev, subcred = new_device(m, "aokafor", "teacher123")
    for target in ("secondsub", "admin"):
        row = rows[target]
        r = push(subdev, subcred, [change("users", dict(name=row["name"], username=target, role=row["role"], password_hash=hashed("Hijack-99")),
                                          client_uuid=row["client_uuid"], base_updated_at=row["updated_at"])])
        assert r[0]["status"] == "error", target
    assert login(m.app.test_client(), "admin", "Hijack-99").status_code != 302


def test_offline_grading_edit_rules():
    m, ids = _ctx()
    import db
    conn = db.get_db()
    cfg = dict(conn.execute("SELECT * FROM grading_config").fetchone())
    conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,15,10,55)",
                 (ids["student"], ids["subj"], ids["term"]))
    conn.commit()
    conn.close()
    admin_dev, admin_cred = new_device(m, "admin", "admin123")
    teacher_dev, teacher_cred = new_device(m, "aokafor", "teacher123")
    def edit(dev, cred, **kw):
        base = {k: cfg[k] for k in ("ca1_max", "ca2_max", "ca3_max", "exam_max")}
        base.update(kw)
        return push(dev, cred, [change("grading_config", base, client_uuid=cfg["client_uuid"],
                                       base_updated_at=cfg["updated_at"], base_data={k: cfg[k] for k in base})])[0]
    assert edit(teacher_dev, teacher_cred, ca3_max=10, exam_max=50)["status"] == "error"          # teachers can't
    assert edit(admin_dev, admin_cred, exam_max=70)["status"] == "error"                            # 20+20+70 > 100
    assert edit(admin_dev, admin_cred, ca1_max=10, ca2_max=10, exam_max=70)["status"] == "error"    # would drop below the saved 55? no: 55<=70 ok, but CA1 15 > 10
    assert edit(admin_dev, admin_cred, ca1_max=-5)["status"] == "error"
    ok = edit(admin_dev, admin_cred, ca1_max=20, ca2_max=10, ca3_max=10, exam_max=60)               # enable CA3, still 100
    assert ok["status"] == "synced", ok
    conn = db.get_db()
    row = conn.execute("SELECT ca2_max, ca3_max FROM grading_config").fetchone()
    assert (row[0], row[1]) == (10, 10)
    assert conn.execute("SELECT COUNT(*) FROM grading_config").fetchone()[0] == 1
    conn.close()


def test_staff_attendance_status_is_validated():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    import db
    conn = db.get_db()
    tid = conn.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0]
    conn.close()
    ok = push(dev, cred, [change("staff_attendance", dict(user_id=tid, date="2026-09-14", status="Late", recorded_by=tid))])
    assert ok[0]["status"] == "synced"
    bad = push(dev, cred, [change("staff_attendance", dict(user_id=tid, date="2026-09-15", status="Sleeping", recorded_by=tid)),
                           change("staff_attendance", dict(user_id=tid, date="not-a-date", status="Present", recorded_by=tid))])
    assert [r["status"] for r in bad] == ["error", "error"]


def test_grade_bands_can_be_added_and_edited_from_a_device_with_the_same_rules_as_online():
    m, ids = _ctx()
    admin_dev, admin_cred = new_device(m, "admin", "admin123")
    teacher_dev, teacher_cred = new_device(m, "aokafor", "teacher123")
    boot = bootstrap(admin_dev, admin_cred)["entities"]["grade_scale"]
    band = next(b for b in boot if b["grade"] == "A")
    def edit(dev, cred, row, **kw):
        data = {k: row[k] for k in ("grade", "min_score", "max_score", "remark")}
        data.update(kw)
        return push(dev, cred, [change("grade_scale", data, client_uuid=row["client_uuid"], base_updated_at=row["updated_at"],
                                       base_data={k: row[k] for k in data})])[0]
    assert edit(teacher_dev, teacher_cred, band, remark="hacked")["status"] == "error"                  # teachers can't
    assert edit(admin_dev, admin_cred, band, min_score=90, max_score=50)["status"] == "error"           # min above max
    assert edit(admin_dev, admin_cred, band, min_score=-5)["status"] == "error"
    assert edit(admin_dev, admin_cred, band, min_score=40)["status"] == "error"                         # would overlap the band below
    ok = edit(admin_dev, admin_cred, band, remark="Outstanding")
    assert ok["status"] == "synced", ok
    new = push(admin_dev, admin_cred, [change("grade_scale", dict(grade="A+", min_score=99, max_score=100, remark="Top"))])
    assert new[0]["status"] == "error"                                                                    # overlaps A (70-100)
    import db
    conn = db.get_db()
    conn.execute("UPDATE grade_scale SET max_score=98 WHERE grade='A'")                                  # make room, as an admin would online
    conn.commit()
    conn.close()
    room = push(admin_dev, admin_cred, [change("grade_scale", dict(grade="A+", min_score=99, max_score=100, remark="Top"))])
    assert room[0]["status"] == "synced"
    conn = db.get_db()
    assert conn.execute("SELECT remark FROM grade_scale WHERE grade='A'").fetchone()[0] == "Outstanding"
    conn.close()


def test_online_grade_band_screen_refuses_overlaps_and_bad_limits():
    m, ids = _ctx()
    from helpers import login, csrf
    c = m.app.test_client()
    login(c, "admin", "admin123")
    r = c.post("/admin/grading/scale/add", data={"csrf_token": csrf(c), "grade": "X", "min_score": "50", "max_score": "95", "remark": "x"}, follow_redirects=True)
    assert b"overlaps" in r.data
    r = c.post("/admin/grading/scale/add", data={"csrf_token": csrf(c), "grade": "X", "min_score": "80", "max_score": "20", "remark": "x"}, follow_redirects=True)
    assert b"can&#39;t be higher" in r.data or b"higher than" in r.data


def test_notifications_are_visible_per_school_and_role_and_can_be_marked_read():
    m, ids = _ctx()
    b = make_school(m)
    import db
    conn = db.get_db()
    school = conn.execute("SELECT id FROM schools WHERE name!='School B'").fetchone()[0]
    conn.execute("INSERT INTO notifications (sender_label, school_id, target_role, title, message) VALUES ('Platform', NULL, 'all', 'Everyone', 'hello all')")
    conn.execute("INSERT INTO notifications (sender_label, school_id, target_role, title, message) VALUES ('Admin: A', ?, 'teacher', 'Teachers of A', 'staff meeting')", (school,))
    conn.execute("INSERT INTO notifications (sender_label, school_id, target_role, title, message) VALUES ('Admin: B', ?, 'all', 'School B secret', 'b only')", (b["school_id"],))
    conn.execute("INSERT INTO notifications (sender_label, school_id, target_role, title, message) VALUES ('Admin: A', ?, 'student', 'For pupils', 'not for staff')", (school,))
    conn.commit()
    conn.close()
    dev, cred = new_device(m, "aokafor", "teacher123")
    r = dev.get("/api/sync/notifications", headers=device_headers(cred)).get_json()
    titles = {i["title"] for i in r["items"]}
    assert titles == {"Everyone", "Teachers of A"}                    # not School B's, not the pupils' notice
    assert r["last_seen_id"] == 0
    assert dev.post("/api/sync/notifications/seen", headers=device_headers(cred)).status_code == 200
    assert dev.get("/api/sync/notifications", headers=device_headers(cred)).get_json()["last_seen_id"] > 0


def test_material_listings_follow_the_online_visibility_rule_and_stay_in_their_school():
    m, ids = _ctx()
    b = make_school(m)
    import db
    conn = db.get_db()
    school = conn.execute("SELECT id FROM schools WHERE name!='School B'").fetchone()[0]
    sess = conn.execute("SELECT id FROM sessions WHERE school_id=?", (school,)).fetchone()[0]
    conn.execute("INSERT INTO classes (school_id, name) VALUES (?, 'JSS2A')", (school,))
    other_cls = conn.execute("SELECT id FROM classes WHERE name='JSS2A'").fetchone()[0]
    def add(title, cls, sid=school, session=sess, subject=ids["subj"]):
        conn.execute("INSERT INTO materials (school_id, session_id, class_id, subject_id, title, kind, filename) VALUES (?,?,?,?,?,?,?)",
                     (sid, session, cls, subject, title, "Notes", "x.pdf"))
    add("Her class", ids["cls"])
    add("Another class", other_cls)
    add("School B secret", b["class_id"], sid=b["school_id"], session=b["term_id"], subject=b["subject_id"])
    conn.commit()
    conn.close()
    adm_dev, adm_cred = new_device(m, "admin", "admin123")
    tch_dev, tch_cred = new_device(m, "aokafor", "teacher123")      # form teacher of JSS1A only
    got = lambda dev, cred: {r["title"] for r in bootstrap(dev, cred)["entities"]["materials"]}
    assert got(adm_dev, adm_cred) == {"Her class", "Another class"}
    assert got(tch_dev, tch_cred) == {"Her class"}
    # read-only from a device
    row = bootstrap(adm_dev, adm_cred)["entities"]["materials"][0]
    r = push(adm_dev, adm_cred, [change("materials", dict(title="hacked"), client_uuid=row["client_uuid"], base_updated_at=row["updated_at"])])
    assert r[0]["status"] == "error"


def test_paging_never_repeats_finished_entities():
    """Regression: with more than one page of data, every page used to re-send the
    entities that were already complete (a 1,200-pupil school downloaded ~450 MB)."""
    m, ids = _ctx()
    import db
    conn = db.get_db()
    for n in range(4, 41):
        cur = conn.execute("INSERT INTO students (admission_no, first_name, last_name, gender, class_id) VALUES (?,?,?,?,?)",
                           (f"{n:03d}", f"P{n}", f"S{n}", "M", ids["cls"]))
        conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,5,5,5)",
                     (cur.lastrowid, ids["subj"], ids["term"]))
    conn.commit()
    expected = {"students": conn.execute("SELECT COUNT(*) FROM students").fetchone()[0],
                "scores": conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0],
                "classes": conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0]}
    conn.close()
    dev, cred = new_device(m, "admin", "admin123")
    for url_base in ("/api/sync/bootstrap?limit=7", "/api/sync/pull?since=2000-01-01T00:00:00&limit=7"):
        seen, totals, cursor, pages = {}, {}, None, 0
        while True:
            url = url_base + (f"&cursor={cursor}" if cursor else "")
            j = dev.get(url, headers=device_headers(cred)).get_json()
            pages += 1
            for name, rows in j["entities"].items():
                totals[name] = totals.get(name, 0) + len(rows)
                seen.setdefault(name, set()).update(r["client_uuid"] for r in rows)
            cursor = j.get("cursor")
            if not cursor:
                break
            assert pages < 100
        for name, want in expected.items():
            assert totals[name] == len(seen[name]) == want, (url_base, name, totals[name], len(seen[name]), want)
        assert totals["classes"] == expected["classes"]              # small entity sent exactly once, not once per page


def test_sync_answers_are_gzipped_when_asked_and_identical_when_decoded():
    import gzip, json as _json
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    plain = dev.get("/api/sync/bootstrap", headers=device_headers(cred))
    zipped = dev.get("/api/sync/bootstrap", headers={**device_headers(cred), "Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in plain.headers
    assert zipped.headers.get("Content-Encoding") == "gzip" and len(zipped.data) < len(plain.data) / 2
    a, b = _json.loads(plain.data), _json.loads(gzip.decompress(zipped.data))
    a.pop("generated_at"); b.pop("generated_at")
    assert a == b
