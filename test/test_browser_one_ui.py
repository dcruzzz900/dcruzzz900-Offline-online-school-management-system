"""One UI, online and offline. In a real browser:
  - after login staff land in the app (the same screens whether or not there is a
    connection); nothing is uploaded by hand - saved entries sync by themselves;
  - a small indicator shows exactly three states;
  - students / subject assignments can be edited with no connection;
  - a second device does first-time setup by itself;
  - one school's data never appears in another school's account on the same device."""
import re
import time

from helpers import fresh_app, LiveServer, make_school, wait_until

try:
    from playwright.sync_api import sync_playwright
except Exception:          # pragma: no cover
    sync_playwright = None


def _login(page, base, user, password):
    page.goto(base + "/login")
    page.fill("input[name=username]", user)
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_url(re.compile(r".*/app$"))
    page.wait_for_selector("h1")


def _pill(page):
    return page.evaluate("document.getElementById('syncPill') && document.getElementById('syncPill').textContent")


def _wait_pill(page, fragment, timeout=25):
    wait_until(page, f"(document.getElementById('syncPill') && document.getElementById('syncPill').textContent.includes({fragment!r}))", timeout=timeout)


def _wait_db(fn, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.4)
    raise AssertionError("server never received it")


def test_one_ui_online_and_offline_with_automatic_sync_and_first_time_setup():
    if sync_playwright is None:
        return
    m, _ = fresh_app()
    import db
    conn = db.get_db()
    ids = dict(school=conn.execute("SELECT id FROM schools").fetchone()[0],
               cls=conn.execute("SELECT id FROM classes").fetchone()[0],
               subj=[r[0] for r in conn.execute("SELECT id FROM subjects ORDER BY id")],
               students=[r[0] for r in conn.execute("SELECT id FROM students ORDER BY id")],
               teacher=conn.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0])
    import os as _os
    import app as _appmod
    _dir = _os.path.join(_appmod.MATERIALS_DIR, str(ids["school"]))
    _os.makedirs(_dir, exist_ok=True)
    open(_os.path.join(_dir, "unit1.pdf"), "wb").write(b"%PDF-1.4 unit one notes")
    conn.execute("INSERT INTO materials (school_id, session_id, class_id, subject_id, title, kind, filename, original_filename) "
                 "SELECT ?, id, ?, ?, 'Unit 1 Notes', 'Notes', 'unit1.pdf', 'unit1.pdf' FROM sessions LIMIT 1",
                 (ids["school"], ids["cls"], ids["subj"][0]))
    conn.execute("DELETE FROM class_subjects")          # so "Assign Subjects" has something to do
    conn.execute("INSERT INTO notifications (sender_label, school_id, target_role, title, message) VALUES ('Platform', NULL, 'all', 'Term dates', 'Resumption is on Monday')")
    conn.commit()
    conn.close()
    server = LiveServer(m.app).up()
    base = server.base
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            _login(page, base, "admin", "admin123")
            assert "Admin Dashboard" in page.locator("h1").first.inner_text()
            _wait_pill(page, "Online — Synced")
            # the same navigation the server pages have
            nav = page.locator("#navbarLinks").inner_text()
            for label in ("Dashboard", "Classes", "Materials", "Setup", "Terms", "Reports", "Settings", "Logout"):
                assert label in nav, (label, nav)

            # ---- ONLINE: use the normal screens; nothing is uploaded by hand
            page.click("#navbarLinks >> text=Settings")                    # turn on CA3: 15 + 15 + 10 + 60
            page.fill("#wCa1", "15")
            page.fill("#wCa2", "15")
            page.fill("#wCa3", "10")
            page.click("#wSave")
            _wait_db(lambda: __import__("db").get_db().execute("SELECT 1 FROM grading_config WHERE ca3_max=10 AND ca1_max=15").fetchone())

            # grade bands: an overlapping edit is refused on the device; a valid one syncs by itself
            bands = page.locator("div.card:has(h3:has-text('Edit grade bands'))")
            first = bands.locator("tbody tr").nth(0)
            original_min = first.locator(".gbMin").input_value()
            first.locator(".gbMin").fill("1")
            first.locator("button").click()
            page.wait_for_function("document.querySelector('#gbMsg').textContent.includes('overlaps')", timeout=25000)
            first.locator(".gbMin").fill(original_min)
            first.locator(".gbR").fill("Outstanding!")
            first.locator("button").click()
            _wait_db(lambda: __import__("db").get_db().execute("SELECT 1 FROM grade_scale WHERE remark='Outstanding!'").fetchone())

            page.click("#navbarLinks >> text=Setup")
            page.click("#offlineRoot a:has-text('Assign Subjects')")
            page.select_option("#asClass", str(ids["cls"]))
            page.wait_for_selector("#asBody select")
            page.locator("#asBody select").nth(0).select_option(str(ids["teacher"]))
            assigned = _wait_db(lambda: __import__("db").get_db().execute("SELECT subject_id FROM class_subjects WHERE teacher_id=?", (ids["teacher"],)).fetchone())[0]

            page.click("#navbarLinks >> text=Setup")
            page.click("#offlineRoot a:has-text('Students')")
            page.wait_for_selector("#stBody tr td button")
            page.locator("#stBody tr td button").nth(0).click()
            page.fill("#esParent", "Mrs Parent Edited")
            page.click("#esSave")
            _wait_db(lambda: __import__("db").get_db().execute("SELECT 1 FROM students WHERE parent_name='Mrs Parent Edited'").fetchone())
            _wait_pill(page, "Online — Synced")

            # materials: listed from the device's own data; saved for offline while connected
            page.click("#navbarLinks >> text=Materials")
            page.wait_for_selector("text=Unit 1 Notes")
            page.click("button:has-text('Save for offline')")
            page.wait_for_selector("button:has-text('Open')")

            # ---- OFFLINE: same screens, indicator changes, work is saved on the device
            ctx.set_offline(True)
            server.down()
            _wait_pill(page, "Offline — Saved Locally")
            page.click("#navbarLinks >> text=Terms")                       # needs the server: says so, doesn't break
            page.wait_for_function("document.body.innerText.includes('needs an internet connection')")
            page.click("#navbarLinks >> text=Dashboard")
            page.click("#dashWork >> text=Score Entry")
            page.select_option("#seClassSelect", str(ids["cls"]))
            wait_until(page, "document.querySelectorAll('#seSubjectSelect option').length > 1")
            page.select_option("#seSubjectSelect", str(assigned))
            page.wait_for_selector("tr[data-student] input.ca1")
            page.locator("tr[data-student] input.ca1").nth(0).fill("12")
            page.click("#saveScoresBtn")
            page.wait_for_function("document.querySelector('#scoreMsg').textContent.includes('Saved 1 score row')", timeout=25000)
            assert "Offline" in _pill(page)

            page.click("#navbarLinks >> text=Notifications")                # cached from the last sync: readable offline
            page.wait_for_selector("text=Resumption is on Monday")
            page.click("#navbarLinks >> text=Materials")                     # the saved file opens with no server at all
            with page.expect_download() as dl:
                page.click("button:has-text('Open')")
            assert open(dl.value.path(), "rb").read().startswith(b"%PDF-1.4 unit one notes")

            # ---- more screens that used to be server-only: staff attendance, roll-call history, cumulative results
            page.click("#navbarLinks >> text=Staff Attendance")
            page.wait_for_selector("tr[data-user]")
            page.locator("tr[data-user]", has_text="Okafor").locator("input[value=Late]").check()
            page.click("#saSave")
            page.wait_for_function("document.querySelector('#saMsg') && document.querySelector('#saMsg').textContent.includes('Saved ')", timeout=25000)
            page.click("#navbarLinks >> text=Dashboard")
            page.click("#dashWork >> text=Roll-Call History")
            page.wait_for_selector("text=Per student")
            page.click("#navbarLinks >> text=Classes")
            page.click("#rsLoad")
            page.click("#rsCum")
            page.wait_for_selector(".sheetView iframe")
            assert "Cumulative Broadsheet" in page.frame_locator(".sheetView iframe").locator("body").inner_text()

            # ---- connection returns: automatic sync, no upload button pressed
            ctx.set_offline(False)
            server.up()
            _wait_db(lambda: __import__("db").get_db().execute("SELECT 1 FROM scores WHERE ca1=12").fetchone(), timeout=40)
            _wait_pill(page, "Online — Synced", timeout=40)
            _wait_db(lambda: __import__("db").get_db().execute("SELECT 1 FROM staff_attendance WHERE status='Late' AND user_id=?", (ids["teacher"],)).fetchone(), timeout=40)

            # ---- second device: first-time setup happens by itself
            ctx2 = browser.new_context()
            page2 = ctx2.new_page()
            _login(page2, base, "admin", "admin123")
            wait_until(page2, f"OfflineDB.getMeta({ids['school']}, 'last_sync_at').then(v => !!v)", timeout=40)
            page2.click("#navbarLinks >> text=Dashboard")
            page2.wait_for_selector(".stat-box .num")
            assert page2.locator(".stat-box .num").first.inner_text() == "3"           # its own copy of the school's data
            assert page2.evaluate(f"OfflineDB.getAll({ids['school']}, 'scores').then(r => r.length)") >= 1   # including the score entered on device 1
            browser.close()
    finally:
        server.down()


def test_one_schools_data_never_appears_in_another_schools_account_on_a_shared_device():
    if sync_playwright is None:
        return
    m, _ = fresh_app()
    b = make_school(m, name="School B", admin_username="adminb", password="pass-b-123")
    import db
    conn = db.get_db()
    a_school = conn.execute("SELECT id FROM schools WHERE name!='School B'").fetchone()[0]
    conn.close()
    server = LiveServer(m.app).up()
    base = server.base
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            _login(page, base, "admin", "admin123")                          # School A
            wait_until(page, f"OfflineDB.getMeta({a_school}, 'last_sync_at').then(v => !!v)", timeout=40)
            page.click("#navbarLinks >> text=Setup")
            page.click("#offlineRoot a:has-text('Students')")
            page.wait_for_selector("#stBody tr")
            assert "Amaka" in page.inner_text("body") or "Eze" in page.inner_text("body")
            page.click("#navbarLinks >> text=Logout")
            page.wait_for_url(re.compile(r".*/login"))

            _login(page, base, "adminb", "pass-b-123")                       # School B, same browser
            wait_until(page, f"OfflineDB.getMeta({b['school_id']}, 'last_sync_at').then(v => !!v)", timeout=40)
            page.click("#navbarLinks >> text=Setup")
            page.click("#offlineRoot a:has-text('Students')")
            page.wait_for_selector("#stBody tr")
            text = page.inner_text("body")
            assert "Bola" in text and "Amaka" not in text and "Eze" not in text
            b_names = page.evaluate(f"OfflineDB.getAll({b['school_id']}, 'students').then(r => r.map(x => x.first_name))")
            assert b_names == ["Bola"], b_names
            for entity in ("classes", "subjects", "users"):
                names = page.evaluate(f"OfflineDB.getAll({b['school_id']}, '{entity}').then(r => r.map(x => x.name))")
                assert not any(n in ("JSS1A", "Mathematics", "Administrator") for n in names), (entity, names)
            page.click("#navbarLinks >> text=Logout")
            page.wait_for_url(re.compile(r".*/login"))

            # ---- offline on the shared device: each person can only open their OWN school
            page.close()
            page = ctx.new_page()
            ctx.set_offline(True)
            server.down()
            page.goto(base + "/dashboard")
            page.wait_for_selector("button:has-text('Administrator'), button:has-text('School B')")
            page.click("button:has-text('School B Admin')")
            page.fill("#pwInput", "admin123")                                  # School A's password on School B's account
            page.click("#unlockBtn")
            page.wait_for_function("document.querySelector('#pwError').textContent.includes('Incorrect')", timeout=15000)
            page.fill("#pwInput", "pass-b-123")
            page.click("#unlockBtn")
            page.wait_for_selector("h1:has-text('Admin Dashboard')")
            assert "Amaka" not in page.inner_text("body")
            page.click("#navbarLinks >> text=Setup")
            page.click("#offlineRoot a:has-text('Students')")
            page.wait_for_selector("#stBody tr")
            assert "Bola" in page.inner_text("body") and "Amaka" not in page.inner_text("body")
            browser.close()
    finally:
        server.down()
