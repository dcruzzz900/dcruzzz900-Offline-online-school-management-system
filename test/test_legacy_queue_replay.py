"""Phones running the EARLIER build may hold forms queued while offline. Their queue module replays
them with an offline_token and an X-Offline-Sync header and expects {ok, id} JSON back (so dependent
queued items can be resolved). The upgraded server must speak that protocol, and a replay whose reply
was lost must not create a duplicate."""
from helpers import fresh_app, login, csrf


def _post(c, url, data, offline=True):
    data = {**data, "csrf_token": csrf(c)}
    return c.post(url, data=data, headers={"X-Offline-Sync": "1"} if offline else {})


def _admin():
    m, _ = fresh_app()
    c = m.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    return m, c


def test_class_subject_student_and_teacher_replays_return_ids_and_are_idempotent():
    m, c = _admin()
    import db
    conn = db.get_db()
    count = lambda sql: conn.execute(sql).fetchone()[0]

    r1 = _post(c, "/admin/classes", {"name": "Legacy Class", "offline_token": "tok-class-1"}).get_json()
    r2 = _post(c, "/admin/classes", {"name": "Legacy Class", "offline_token": "tok-class-1"}).get_json()      # reply was lost, so it is sent again
    assert r1["ok"] and r2["ok"] and r1["id"] == r2["id"]
    assert count("SELECT COUNT(*) FROM classes WHERE name='Legacy Class'") == 1

    s1 = _post(c, "/admin/subjects", {"name": "Legacy Subject", "offline_token": "tok-sub-1"}).get_json()
    s2 = _post(c, "/admin/subjects", {"name": "Legacy Subject", "offline_token": "tok-sub-1"}).get_json()
    assert s1["ok"] and s1["id"] == s2["id"] and count("SELECT COUNT(*) FROM subjects WHERE name='Legacy Subject'") == 1

    dup = _post(c, "/admin/classes", {"name": "Legacy Class", "offline_token": "tok-class-2"})              # a genuine duplicate is reported, not created
    assert dup.status_code == 409 and dup.get_json()["ok"] is False

    t1 = _post(c, "/admin/teachers", {"name": "Queued Teacher", "username": "queuedt", "password": "queued-pass-1", "offline_token": "tok-t-1"}).get_json()
    t2 = _post(c, "/admin/teachers", {"name": "Queued Teacher", "username": "queuedt", "password": "queued-pass-1", "offline_token": "tok-t-1"}).get_json()
    assert t1["ok"] and t1["id"] == t2["id"] and count("SELECT COUNT(*) FROM users WHERE username='queuedt'") == 1

    st = {"admission_no": "L001", "first_name": "Late", "last_name": "Arrival", "gender": "F", "class_id": str(r1["id"]), "offline_token": "tok-st-1"}
    a = _post(c, "/admin/students", st).get_json()
    b = _post(c, "/admin/students", st).get_json()
    assert a["ok"] and a["id"] == b["id"] and count("SELECT COUNT(*) FROM students WHERE admission_no='L001'") == 1
    conn.close()


def test_the_queue_module_is_the_earlier_builds_and_keys_are_per_school():
    import os
    from helpers import ROOT
    js = open(os.path.join(ROOT, "static", "js", "offline-queue.js"), encoding="utf-8").read()
    assert '"offline_queue_v1:" + SCHOOL_ID' in js          # the key phones already hold data under
    m, c = _admin()
    assert 'data-auth-school-id="' in c.get("/admin/promote").get_data(as_text=True)


def test_a_phone_upgraded_with_items_still_queued_by_the_earlier_build_sends_them_with_dependencies():
    """Real browser: the earlier build left a queued class AND a student that depends on that class's
    not-yet-existing id. After the upgrade the app tells the person, and the Offline Queue page sends
    both, in order, resolving the placeholder id."""
    import json
    import re
    from helpers import LiveServer, wait_until
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return
    m, _ = fresh_app()
    import db
    school = db.get_db().execute("SELECT id FROM schools").fetchone()[0]
    server = LiveServer(m.app).up()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto(server.base + "/login")
            page.fill("input[name=username]", "admin")
            page.fill("input[name=password]", "admin123")
            page.click("button[type=submit]")
            page.wait_for_url(re.compile(r".*/app$"))
            wait_until(page, f"OfflineDB.getMeta({school}, 'last_sync_at').then(v => !!v)", timeout=40)
            queue = [
                {"id": "draft_1_a", "action": "/admin/classes", "fields": [["name", "Queued JSS9"], ["category", ""], ["offline_token", "tok-q-class"]],
                 "entityType": "class", "localId": "local_class_1_abc", "label": "Class Queued JSS9", "queued_at": "2026-09-01T10:00:00Z", "attempts": 0},
                {"id": "draft_2_b", "action": "/admin/students",
                 "fields": [["admission_no", "Q001"], ["first_name", "Queued"], ["last_name", "Pupil"], ["gender", "F"], ["class_id", "local_class_1_abc"], ["offline_token", "tok-q-student"]],
                 "entityType": "student", "localId": "local_student_2_def", "dependsOn": ["local_class_1_abc"], "label": "Student Queued Pupil", "queued_at": "2026-09-01T10:01:00Z", "attempts": 0},
            ]
            page.evaluate("(q) => localStorage.setItem('offline_queue_v1:' + arguments[0], JSON.stringify(q))".replace("arguments[0]", str(school)), queue)
            page.reload()
            page.wait_for_selector("text=saved by the previous version")
            page.click("a:has-text('Send them now')")
            page.wait_for_selector("#syncNowBtn")
            page.click("#syncNowBtn")
            import time as _t
            end = _t.time() + 40
            while _t.time() < end:                                   # wait until the server really has both
                c2 = db.get_db()
                done = c2.execute("SELECT 1 FROM students WHERE admission_no='Q001'").fetchone()
                c2.close()
                if done:
                    break
                _t.sleep(0.5)
            browser.close()
    finally:
        server.down()
    conn = db.get_db()
    cls = conn.execute("SELECT id FROM classes WHERE name='Queued JSS9'").fetchone()
    assert cls is not None
    stu = conn.execute("SELECT class_id FROM students WHERE admission_no='Q001'").fetchone()
    assert stu is not None and stu["class_id"] == cls["id"]          # the placeholder id was replaced with the real one
    conn.close()
