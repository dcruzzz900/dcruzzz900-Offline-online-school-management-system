"""V109: role-specific dashboard charts built ONLY from real database rows.

Every function returns a list of chart specs: {id, title, subtitle, type, labels, datasets:[{label,data}], empty}. A chart with nothing to
show says so (`empty`), it is never padded with invented numbers. Records that cannot be plotted (for example students with no admission date)
are counted in the subtitle instead of silently dropped. All queries are scoped to the school (or, for the Super Admin, the platform)."""
import datetime


def _months(n=12, today=None):
    today = today or datetime.date.today()
    y, m, out = today.year, today.month, []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _label(ym):
    y, m = ym.split("-")
    return f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(m) - 1]} {y}"


def _spec(cid, title, kind, labels, datasets, subtitle="", empty_msg="No data recorded for this selection yet.", stacked=False, unit=""):
    has = any(any((v or 0) for v in d["data"]) for d in datasets) and bool(labels)
    return {"id": cid, "title": title, "subtitle": subtitle, "type": kind, "labels": labels, "datasets": datasets, "stacked": stacked,
            "unit": unit, "empty": None if has else empty_msg}


# ----------------------------------------------------------------------------- Teacher / School Admin
def teaching_specs(conn, school_id, term, class_ids, stats_fn, compute_total):
    """Subject performance + pass/fail distribution for the given classes and term (stats_fn = class_term_result_stats)."""
    if not term or not class_ids:
        return [_spec("rcSubjects", "Subject performance", "bar", [], [], empty_msg="Set an active term and assign classes to see this."),
                _spec("rcPassFail", "Pass and fail distribution", "doughnut", [], [], empty_msg="Set an active term and assign classes to see this.")]
    ph = ",".join("?" * len(class_ids))
    rows = conn.execute(
        f"SELECT sub.name AS subject, sc.ca1, sc.ca2, sc.ca3, sc.exam FROM scores sc "
        f"JOIN students st ON st.id=sc.student_id AND st.is_active=1 AND COALESCE(st.is_deleted,0)=0 "
        f"JOIN subjects sub ON sub.id=sc.subject_id JOIN classes c ON c.id=st.class_id "
        f"WHERE sc.term_id=? AND COALESCE(sc.is_deleted,0)=0 AND c.school_id=? AND c.id IN ({ph})", (term["id"], school_id, *class_ids)).fetchall()
    acc = {}
    for r in rows:
        acc.setdefault(r["subject"], []).append(compute_total(r["ca1"], r["ca2"], r["exam"], r["ca3"]))
    names = sorted(acc)
    avgs = [round(sum(acc[n]) / len(acc[n]), 1) for n in names]
    passed = failed = not_assessed = 0
    for cid in class_ids:
        s = stats_fn(conn, school_id, cid, term["id"])
        passed += s["passed"]; failed += s["failed"]; not_assessed += s["not_assessed"]
    return [
        _spec("rcSubjects", "Subject performance", "bar", names, [{"label": "Average score", "data": avgs}],
              subtitle=f"Average total score per subject, {term['name']}.", unit=""),
        _spec("rcPassFail", "Pass and fail distribution", "doughnut", ["Passed", "Failed", "Not yet assessed"],
              [{"label": "Students", "data": [passed, failed, not_assessed]}],
              subtitle="Students with at least one score are counted as passed or failed; others are shown separately."),
    ]


# ----------------------------------------------------------------------------- Registrar
def registrar_specs(conn, school_id, today=None):
    months = _months(12, today)
    idx = {m: i for i, m in enumerate(months)}
    adm = [0] * 12
    undated = 0
    for r in conn.execute("SELECT date_of_admission d FROM students WHERE school_id=? AND COALESCE(is_deleted,0)=0", (school_id,)).fetchall():
        d = (r["d"] or "").strip()
        if not d:
            undated += 1
        elif d[:7] in idx:
            adm[idx[d[:7]]] += 1
    trans, wd, other = [0] * 12, [0] * 12, [0] * 12
    for r in conn.execute("SELECT new_status s, COALESCE(effective_date, substr(server_timestamp,1,10)) d FROM student_status_history WHERE school_id=?", (school_id,)).fetchall():
        s, d = (r["s"] or "").strip().lower(), (r["d"] or "")[:7]
        if d not in idx or s in ("active", ""):
            continue
        (trans if s.startswith("transfer") else wd if s.startswith("withdr") else other)[idx[d]] += 1
    cls = conn.execute("SELECT c.name, COUNT(s.id) n FROM classes c LEFT JOIN students s ON s.class_id=c.id AND s.is_active=1 AND COALESCE(s.is_deleted,0)=0 "
                       "WHERE c.school_id=? GROUP BY c.id ORDER BY c.name", (school_id,)).fetchall()
    labels = [_label(m) for m in months]
    note = f" {undated} student(s) have no admission date recorded and are not shown." if undated else ""
    return [
        _spec("rcAdmissions", "New admissions", "bar", labels, [{"label": "Admitted", "data": adm}], subtitle="Students admitted per month, last 12 months." + note),
        _spec("rcMovements", "Transfers and withdrawals", "bar", labels,
              [{"label": "Transferred", "data": trans}, {"label": "Withdrawn", "data": wd}, {"label": "Other status changes", "data": other}],
              subtitle="Status changes recorded in the student status history.", stacked=True),
        _spec("rcEnrolment", "Student enrolment by class", "bar", [r["name"] for r in cls], [{"label": "Active students", "data": [r["n"] for r in cls]}],
              subtitle="Current active enrolment."),
    ]


# ----------------------------------------------------------------------------- Super Admin (platform)
def platform_specs(conn, today=None):
    months = _months(12, today)
    idx = {m: i for i, m in enumerate(months)}
    reg = [0] * 12
    before = 0
    for r in conn.execute("SELECT created_at c FROM schools").fetchall():
        c = (r["c"] or "")[:7]
        if c in idx:
            reg[idx[c]] += 1
        elif c and c < months[0]:
            before += 1
    cum, run = [], before
    for v in reg:
        run += v
        cum.append(run)
    active = suspended = inactive = 0
    for r in conn.execute("SELECT is_suspended, is_archived, activation_status FROM schools").fetchall():
        if r["is_suspended"]:
            suspended += 1
        elif r["is_archived"] or (r["activation_status"] or "") != "active":
            inactive += 1
        else:
            active += 1
    per = conn.execute("SELECT sc.name, COUNT(st.id) n FROM schools sc LEFT JOIN students st ON st.school_id=sc.id AND st.is_active=1 AND COALESCE(st.is_deleted,0)=0 "
                       "GROUP BY sc.id ORDER BY n DESC, sc.name LIMIT 10").fetchall()
    labels = [_label(m) for m in months]
    return [
        _spec("rcSchoolStatus", "Schools by status", "doughnut", ["Active", "Suspended", "Inactive"], [{"label": "Schools", "data": [active, suspended, inactive]}],
              subtitle="Inactive = not yet activated, or archived."),
        _spec("rcRegistrations", "School registration trend", "bar", labels, [{"label": "New schools", "data": reg}], subtitle="Schools registered per month, last 12 months."),
        _spec("rcGrowth", "School growth", "line", labels, [{"label": "Total schools", "data": cum}], subtitle="Cumulative number of registered schools."),
        _spec("rcEnrolmentSchools", "Student enrolment across schools", "bar", [r["name"] for r in per], [{"label": "Active students", "data": [r["n"] for r in per]}],
              subtitle="The ten largest schools by active enrolment."),
    ]
