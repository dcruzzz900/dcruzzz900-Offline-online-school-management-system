"""Attendance dedup rule: one entry per staff member per day (and per student per term per
day), whether recorded online or offline. Also covers spec items 2-3: system-generated
timestamp, online/offline provenance, and preserving the original time on late sync."""
from helpers import fresh_app, new_device, push, change, device_headers


def _ctx():
    m, _ = fresh_app()
    import db
    conn = db.get_db()
    ids = dict(
        term=conn.execute("SELECT id FROM terms").fetchone()[0],
        cls=conn.execute("SELECT id FROM classes WHERE name='JSS1A'").fetchone()[0],
        student=conn.execute("SELECT id FROM students ORDER BY id").fetchone()[0],
        teacher=conn.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0],
    )
    conn.close()
    return m, ids


# ---------------------------------------------------------------- staff attendance

def test_one_staff_entry_per_person_per_day_database_level():
    """The UNIQUE(user_id, date) constraint is the hard backstop, independent of the sync
    layer: even a direct insert can't create a second row for the same person/day."""
    m, ids = _ctx()
    import db
    import sqlite3
    conn = db.get_db()
    conn.execute("INSERT INTO staff_attendance (school_id, user_id, date, status, source) "
                 "SELECT school_id, ?, '2026-09-14', 'Present', 'online' FROM users WHERE id=?", (ids["teacher"], ids["teacher"]))
    conn.commit()
    try:
        conn.execute("INSERT INTO staff_attendance (school_id, user_id, date, status, source) "
                     "SELECT school_id, ?, '2026-09-14', 'Absent', 'online' FROM users WHERE id=?", (ids["teacher"], ids["teacher"]))
        conn.commit()
        assert False, "a second row for the same person/day should have been rejected"
    except sqlite3.IntegrityError:
        pass
    conn.close()


def test_two_devices_marking_the_same_staff_member_same_day_merge_to_one_row():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    a = push(dev, cred, [change("staff_attendance", dict(user_id=ids["teacher"], date="2026-09-14", status="Present",
                                                          recorded_by=ids["teacher"], source="online"),
                                client_uuid="a-side", client_ts="2026-09-14T08:00:00Z")])
    assert a[0]["status"] == "synced"
    # A different device, offline that morning, marks the same person "Late" for the same day
    # under its OWN client_uuid (it never saw device A's row) -- must merge to ONE row, not two.
    b = push(dev, cred, [change("staff_attendance", dict(user_id=ids["teacher"], date="2026-09-14", status="Late",
                                                          recorded_by=ids["teacher"], source="offline"),
                                client_uuid="b-side", client_ts="2026-09-14T07:30:00Z")])
    assert b[0]["status"] == "synced"
    import db
    conn = db.get_db()
    rows = conn.execute("SELECT * FROM staff_attendance WHERE user_id=? AND date='2026-09-14'", (ids["teacher"],)).fetchall()
    assert len(rows) == 1, "must never end up with two rows for the same person/day"
    conn.close()


def test_staff_attendance_records_source_and_preserves_original_offline_timestamp():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    # An entry made offline three days before it actually reaches the server.
    r = push(dev, cred, [change("staff_attendance",
                                dict(user_id=ids["teacher"], date="2026-09-10", status="Present",
                                     recorded_by=ids["teacher"], source="offline"),
                                client_uuid="stale-offline", client_ts="2026-09-10T07:05:00")])
    assert r[0]["status"] == "synced"
    import db
    conn = db.get_db()
    row = conn.execute("SELECT source, recorded_at FROM staff_attendance WHERE client_uuid='stale-offline'").fetchone()
    assert row["source"] == "offline"
    assert row["recorded_at"].startswith("2026-09-10T07:05:00"), row["recorded_at"]  # original time kept, not sync time
    conn.close()

    r2 = push(dev, cred, [change("staff_attendance",
                                 dict(user_id=ids["teacher"], date="2026-09-11", status="Present",
                                      recorded_by=ids["teacher"], source="online"),
                                 client_uuid="live-online", client_ts="2026-09-11T07:00:00")])
    assert r2[0]["status"] == "synced"
    conn = db.get_db()
    row2 = conn.execute("SELECT source FROM staff_attendance WHERE client_uuid='live-online'").fetchone()
    assert row2["source"] == "online"
    conn.close()


def test_a_correction_does_not_change_the_original_recorded_at():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    a = push(dev, cred, [change("staff_attendance", dict(user_id=ids["teacher"], date="2026-09-14", status="Absent",
                                                          recorded_by=ids["teacher"], source="offline"),
                                client_uuid="fixme", client_ts="2026-09-14T07:00:00")])
    assert a[0]["status"] == "synced"
    import db
    conn = db.get_db()
    original = conn.execute("SELECT recorded_at FROM staff_attendance WHERE client_uuid='fixme'").fetchone()["recorded_at"]
    conn.close()
    # Authorized correction later in the day (e.g. the person actually came in Late, not Absent)
    b = push(dev, cred, [change("staff_attendance", dict(user_id=ids["teacher"], date="2026-09-14", status="Late",
                                                          recorded_by=ids["teacher"], source="online"),
                                client_uuid="fixme", base_updated_at=a[0]["updated_at"], client_ts="2026-09-14T15:00:00")])
    assert b[0]["status"] == "synced"
    conn = db.get_db()
    row = conn.execute("SELECT status, recorded_at FROM staff_attendance WHERE client_uuid='fixme'").fetchone()
    assert row["status"] == "Late"
    assert row["recorded_at"] == original, "correcting a status must not rewrite when it was ORIGINALLY taken"
    conn.close()


def test_bogus_source_value_is_normalized_not_rejected():
    m, ids = _ctx()
    dev, cred = new_device(m, "admin", "admin123")
    r = push(dev, cred, [change("staff_attendance", dict(user_id=ids["teacher"], date="2026-09-15", status="Present",
                                                          recorded_by=ids["teacher"], source="from-mars"))])
    assert r[0]["status"] == "synced"
    import db
    conn = db.get_db()
    assert conn.execute("SELECT source FROM staff_attendance WHERE date='2026-09-15'").fetchone()["source"] == "online"
    conn.close()


# ---------------------------------------------------------------- student attendance

def test_one_student_entry_per_day_per_term_database_level():
    m, ids = _ctx()
    import db
    import sqlite3
    conn = db.get_db()
    conn.execute("INSERT INTO attendance_records (student_id, class_id, term_id, date, status, source) "
                 "VALUES (?,?,?, '2026-09-14', 'present', 'online')", (ids["student"], ids["cls"], ids["term"]))
    conn.commit()
    try:
        conn.execute("INSERT INTO attendance_records (student_id, class_id, term_id, date, status, source) "
                     "VALUES (?,?,?, '2026-09-14', 'absent', 'online')", (ids["student"], ids["cls"], ids["term"]))
        conn.commit()
        assert False, "a second row for the same student/day/term should have been rejected"
    except sqlite3.IntegrityError:
        pass
    conn.close()


def test_student_attendance_records_source_and_keeps_original_offline_time_after_late_sync():
    m, ids = _ctx()
    dev, cred = new_device(m, "aokafor", "teacher123")
    r = push(dev, cred, [change("attendance_records",
                                dict(student_id=ids["student"], class_id=ids["cls"], term_id=ids["term"],
                                     date="2026-09-10", status="absent", recorded_by=ids["teacher"], source="offline"),
                                client_uuid="stu-offline", client_ts="2026-09-10T08:15:00")])
    assert r[0]["status"] == "synced"
    import db
    conn = db.get_db()
    row = conn.execute("SELECT source, recorded_at, status FROM attendance_records WHERE client_uuid='stu-offline'").fetchone()
    assert row["source"] == "offline" and row["status"] == "absent"
    assert row["recorded_at"].startswith("2026-09-10T08:15:00")
    conn.close()


def test_authorized_correction_of_student_attendance_is_allowed_and_visible():
    """'Allow attendance to be viewed and corrected by authorized users' -- the form teacher
    who took it can fix a mis-tap, and the change reaches the server."""
    m, ids = _ctx()
    dev, cred = new_device(m, "aokafor", "teacher123")
    a = push(dev, cred, [change("attendance_records",
                                dict(student_id=ids["student"], class_id=ids["cls"], term_id=ids["term"],
                                     date="2026-09-14", status="absent", recorded_by=ids["teacher"], source="online"),
                                client_uuid="stu-fix")])
    assert a[0]["status"] == "synced"
    b = push(dev, cred, [change("attendance_records",
                                dict(student_id=ids["student"], class_id=ids["cls"], term_id=ids["term"],
                                     date="2026-09-14", status="present", recorded_by=ids["teacher"], source="online"),
                                client_uuid="stu-fix", base_updated_at=a[0]["updated_at"])])
    assert b[0]["status"] == "synced"
    import db
    conn = db.get_db()
    assert conn.execute("SELECT status FROM attendance_records WHERE client_uuid='stu-fix'").fetchone()["status"] == "present"
    conn.close()
