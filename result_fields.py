"""V104: additional result-sheet information fields (School Admin defines them; form teachers fill them in per student/term)."""
from flask import flash, redirect, render_template, request, session, url_for

TYPES = (("text", "Text (a short note)"), ("number", "Number"), ("choice", "Choice from a list"))


def clean_value(field, raw):
    """-> (stored_value_or_None, error_or_None). Empty clears the value."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    if field["field_type"] == "number":
        try:
            n = float(raw.replace(",", "."))
        except ValueError:
            return None, f"{field['label']}: '{raw}' is not a number"
        try:
            mx = float(field["options"]) if (field["options"] or "").strip() else None
        except ValueError:
            mx = None
        if n < 0 or (mx is not None and n > mx):
            return None, f"{field['label']}: must be between 0 and {mx:g}" if mx is not None else f"{field['label']}: must not be negative"
        return (str(int(n)) if n == int(n) else str(n)), None
    if field["field_type"] == "choice":
        opts = [o.strip() for o in (field["options"] or "").split(",") if o.strip()]
        match = next((o for o in opts if o.lower() == raw.lower()), None)
        return (match, None) if match else (None, f"{field['label']}: '{raw}' is not one of {', '.join(opts)}")
    if any(c in raw for c in "<>"):
        return None, f"{field['label']}: '<' and '>' are not allowed"
    return raw[:200], None


def register_result_fields(app, h):
    get_db, login_required, log_audit = h["get_db"], h["login_required"], h["log_audit"]

    @app.route("/admin/result-fields", methods=["GET", "POST"])
    @login_required("admin", "sub_admin")
    def admin_result_fields():
        sid = session.get("school_id")
        conn = get_db()
        try:
            if request.method == "POST":
                act = request.form.get("action")
                label = " ".join((request.form.get("label") or "").split())[:60]
                ftype = request.form.get("field_type") if request.form.get("field_type") in {t for t, _ in TYPES} else "text"
                options = (request.form.get("options") or "").strip()[:300]
                try:
                    if act == "add":
                        if len(label) < 2 or any(c in label for c in "<>"):
                            raise ValueError("Give the field a name of 2-60 characters (no < or >).")
                        if ftype == "choice" and len([o for o in options.split(",") if o.strip()]) < 2:
                            raise ValueError("A choice field needs at least two options, separated by commas (e.g. Excellent, Good, Fair).")
                        order = conn.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM result_custom_fields WHERE school_id=?", (sid,)).fetchone()[0]
                        conn.execute("INSERT INTO result_custom_fields(school_id,tenant_id,label,field_type,options,sort_order) VALUES (?,?,?,?,?,?)",
                                     (sid, session.get("tenant_id"), label, ftype, options or None, order))
                        msg = "Field added. It now appears in 'Update Result Details' for every student and on the result sheet."
                    else:
                        f = conn.execute("SELECT * FROM result_custom_fields WHERE id=? AND school_id=?", (request.form.get("field_id", type=int), sid)).fetchone()
                        if not f:
                            raise ValueError("That field was not found.")
                        if act == "update":
                            if len(label) < 2 or any(c in label for c in "<>"):
                                raise ValueError("Give the field a name of 2-60 characters (no < or >).")
                            if f["field_type"] == "choice" and len([o for o in options.split(",") if o.strip()]) < 2:
                                raise ValueError("A choice field needs at least two options, separated by commas.")
                            conn.execute("UPDATE result_custom_fields SET label=?, options=?, show_on_sheet=? WHERE id=?",
                                         (label, options or None, 1 if request.form.get("show_on_sheet") else 0, f["id"]))
                            msg = "Field updated."
                        elif act == "toggle":
                            conn.execute("UPDATE result_custom_fields SET is_active=? WHERE id=?", (0 if f["is_active"] else 1, f["id"]))
                            msg = "Field hidden (saved values are kept)." if f["is_active"] else "Field shown again."
                        elif act == "move":
                            ids = [r[0] for r in conn.execute("SELECT id FROM result_custom_fields WHERE school_id=? ORDER BY sort_order, id", (sid,)).fetchall()]
                            i = ids.index(f["id"]); j = i + (-1 if request.form.get("direction") == "up" else 1)
                            if 0 <= j < len(ids):
                                ids[i], ids[j] = ids[j], ids[i]
                                for n, idv in enumerate(ids, 1):
                                    conn.execute("UPDATE result_custom_fields SET sort_order=? WHERE id=? AND school_id=?", (n, idv, sid))
                            msg = "Order updated."
                        else:
                            raise ValueError("Unknown action.")
                    log_audit(conn, "staff", session.get("name"), "result_field_" + (act or "?"), details=label or str(request.form.get("field_id")), school_id=sid)
                    conn.commit()
                    flash(msg, "success")
                except ValueError as exc:
                    conn.rollback()
                    flash(str(exc), "error")
                except Exception:
                    conn.rollback()
                    flash("A field with that name already exists.", "error")
                return redirect(url_for("admin_result_fields"))
            rows = conn.execute("SELECT * FROM result_custom_fields WHERE school_id=? ORDER BY sort_order, id", (sid,)).fetchall()
        finally:
            conn.close()
        return render_template("admin_result_fields.html", rows=rows, types=TYPES)
