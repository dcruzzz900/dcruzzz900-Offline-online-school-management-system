import io
from helpers import fresh_app, login, csrf


def _setup():
    m, _ = fresh_app()
    c = m.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    import db
    conn = db.get_db()
    ids = dict(
        cls=conn.execute("SELECT id FROM classes").fetchone()[0],
        subj=conn.execute("SELECT id FROM subjects ORDER BY id").fetchone()[0],
        stu=[r[0] for r in conn.execute("SELECT id FROM students ORDER BY id")],
    )
    conn.close()
    return m, c, ids


def _post(c, url, data, **kw):
    data = dict(data)
    data["csrf_token"] = csrf(c)
    return c.post(url, data=data, follow_redirects=True, **kw)


def _scores(ids):
    import db
    conn = db.get_db()
    rows = conn.execute("SELECT student_id, ca1, ca2, ca3, exam FROM scores ORDER BY student_id").fetchall()
    conn.close()
    return [tuple(r) for r in rows]


def test_ca3_off_by_default_and_form_unchanged():
    m, c, ids = _setup()
    page = c.get(f"/scores/{ids['cls']}/{ids['subj']}").get_data(as_text=True)
    assert "CA3" not in page
    r = _post(c, f"/scores/{ids['cls']}/{ids['subj']}", {
        "student_id": ids["stu"][0], f"ca1_{ids['stu'][0]}": "15", f"ca2_{ids['stu'][0]}": "10", f"exam_{ids['stu'][0]}": "50"})
    assert b"Scores saved" in r.data
    assert _scores(ids) == [(ids["stu"][0], 15, 10, 0, 50)]
    res = c.get(f"/result/{ids['stu'][0]}").get_data(as_text=True)
    assert "<th>CA3</th>" not in res and ">75.0<" in res or ">75<" in res


def test_enable_ca3_then_enter_totals_grade_pdf_and_csv():
    m, c, ids = _setup()
    r = _post(c, "/admin/grading", {"ca1_max": "10", "ca2_max": "10", "ca3_max": "10", "exam_max": "70"})
    assert b"Grading weights updated" in r.data
    page = c.get(f"/scores/{ids['cls']}/{ids['subj']}").get_data(as_text=True)
    assert "CA3 (/10.0)" in page or "CA3 (/10)" in page
    s0 = ids["stu"][0]
    r = _post(c, f"/scores/{ids['cls']}/{ids['subj']}", {
        "student_id": s0, f"ca1_{s0}": "9", f"ca2_{s0}": "8", f"ca3_{s0}": "7", f"exam_{s0}": "60"})
    assert b"Scores saved" in r.data
    assert _scores(ids) == [(s0, 9, 8, 7, 60)]
    # out-of-range CA3 is refused server-side (the HTML max attribute is not a control)
    r = _post(c, f"/scores/{ids['cls']}/{ids['subj']}", {
        "student_id": s0, f"ca1_{s0}": "9", f"ca2_{s0}": "8", f"ca3_{s0}": "99", f"exam_{s0}": "60"})
    assert b"not saved" in r.data and _scores(ids) == [(s0, 9, 8, 7, 60)]
    res = c.get(f"/result/{s0}").get_data(as_text=True)
    assert "<th>CA3</th>" in res and "84" in res        # 9+8+7+60
    pdf = c.get(f"/result/{s0}/pdf")
    assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
    tpl = c.get(f"/scores/{ids['cls']}/{ids['subj']}/csv_template").get_data(as_text=True)
    assert "admission_no,student_name,ca1,ca2,ca3,exam,total" in tpl
    # CSV upload with CA3, including one out-of-range row that must be skipped
    s1 = ids["stu"][1]
    import db
    conn = db.get_db()
    adm = {r[0]: r[1] for r in conn.execute("SELECT id, admission_no FROM students")}
    conn.close()
    csv_text = ("admission_no,student_name,ca1,ca2,ca3,exam\n"
                f"{adm[s1]},x,10,10,10,70\n"
                f"{adm[ids['stu'][2]]},y,10,10,50,70\n")
    r = c.post(f"/scores/{ids['cls']}/{ids['subj']}/csv_upload", data={
        "csrf_token": csrf(c), "csv_file": (io.BytesIO(csv_text.encode()), "s.csv")},
        content_type="multipart/form-data", follow_redirects=True)
    assert b"Updated scores for 1" in r.data and b"Skipped 1" in r.data
    assert (s1, 10, 10, 10, 70) in _scores(ids)
    hist = c.get(f"/scores/{ids['cls']}/{ids['subj']}/history").get_data(as_text=True)
    assert "CA1/CA2/CA3/Exam" in hist


def test_broadsheet_and_pdf_total_include_ca3():
    m, c, ids = _setup()
    _post(c, "/admin/grading", {"ca1_max": "10", "ca2_max": "10", "ca3_max": "10", "exam_max": "70"})
    s0 = ids["stu"][0]
    _post(c, f"/scores/{ids['cls']}/{ids['subj']}", {
        "student_id": s0, f"ca1_{s0}": "10", f"ca2_{s0}": "10", f"ca3_{s0}": "10", f"exam_{s0}": "70"})
    b = c.get(f"/broadsheet/{ids['cls']}").get_data(as_text=True)
    assert "100" in b
    assert c.get(f"/broadsheet/{ids['cls']}/pdf").data[:4] == b"%PDF"


def test_online_grading_setup_refuses_bad_maximums():
    m, c, ids = _setup()
    s0 = ids["stu"][0]
    _post(c, f"/scores/{ids['cls']}/{ids['subj']}", {"student_id": s0, f"ca1_{s0}": "15", f"ca2_{s0}": "10", f"exam_{s0}": "55"})
    r = _post(c, "/admin/grading", {"ca1_max": "20", "ca2_max": "20", "ca3_max": "20", "exam_max": "60"})     # 120 > 100
    assert b"exceed 100" in r.data
    r = _post(c, "/admin/grading", {"ca1_max": "10", "ca2_max": "20", "ca3_max": "0", "exam_max": "60"})      # below a saved CA1 of 15
    assert b"lowered to" in r.data
    r = _post(c, "/admin/grading", {"ca1_max": "20", "ca2_max": "10", "ca3_max": "10", "exam_max": "60"})
    assert b"Grading weights updated" in r.data


def test_class_arms_created_in_one_go_online_and_via_sync():
    m, c, ids = _setup()
    r = _post(c, "/admin/classes", {"name": "Grade 7", "arms": "A, B ,C, a", "category": ""})
    assert b"Grade 7 A" in r.data and b"Grade 7 C" in r.data
    import db
    conn = db.get_db()
    rows = conn.execute("SELECT name, level, arm FROM classes WHERE level='Grade 7' ORDER BY arm").fetchall()
    assert [tuple(x) for x in rows] == [("Grade 7 A", "Grade 7", "A"), ("Grade 7 B", "Grade 7", "B"), ("Grade 7 C", "Grade 7", "C")]
    r = _post(c, "/admin/classes", {"name": "Grade 7", "arms": "B, D"})       # B exists, D is new
    assert b"Already existed: Grade 7 B" in r.data and b"Added: Grade 7 D" in r.data
    # plain single class still works exactly as before
    r = _post(c, "/admin/classes", {"name": "Nursery 1"})
    assert b"Class &#39;Nursery 1&#39; added" in r.data or b"Nursery 1" in r.data
    conn.close()
    # and a device can create arms too
    from helpers import new_device, push, change
    dev, cred = new_device(m, "admin", "admin123")
    res = push(dev, cred, [change("classes", dict(name="Grade 8 A", level="Grade 8", arm="A")),
                           change("classes", dict(name="Grade 8 B", level="  Grade   8 ", arm="B" * 50))])
    assert [x["status"] for x in res] == ["synced", "synced"]
    conn = db.get_db()
    row = conn.execute("SELECT level, arm FROM classes WHERE name='Grade 8 B'").fetchone()
    assert row["level"] == "Grade 8" and len(row["arm"]) == 20
    conn.close()
