"""V106: renders the two dashboard fragments (shared gender panel, top-students table) for the JSON the React dashboard filter
consumes - through the SAME Jinja macros the full pages use."""
from flask import render_template_string


def render_dashboard_slots(gender, top, scope):
    gender_html = render_template_string(
        '{% from "partials/gender_panel.html" import gender_panel %}{{ gender_panel(g, scope) }}', g=gender or {}, scope=scope)
    top_html = render_template_string(
        '{% from "partials/top_students.html" import top_students_table %}{{ top_students_table(rows, scope) }}', rows=top or [], scope=scope)
    return {"gender_html": gender_html, "top_students_html": top_html}
