"""V100: reportlab rendering of the ONE result-sheet design -- the "Updated Terminal Report Sheet" sample.

Why this exists: downloaded PDFs are normally the print page printed by headless Chromium (html_pdf.py), so
Download == Print. On hosts where Chromium cannot run (typical shared hosting) the system falls back to
reportlab -- and that fallback used to draw a different, older-looking sheet (plain grid, no pale-blue
boxes, no Cumulative/Annual table). This module draws the SAME design as templates/_result_sheet.html +
static/css/result-sheet.css (same sections, same order, same colours, same wording), including the
Cumulative / Annual Performance table, so a download looks like the print view on every host.
"""
import os
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Image, KeepInFrame, Paragraph, Spacer, Table, TableStyle

from db import format_dmy

MARGIN_X = 0.9 * cm
MARGIN_Y = 0.8 * cm
W = A4[0] - 2 * MARGIN_X           # usable width (19.2 cm)
H = A4[1] - 2 * MARGIN_Y
GAP = 0.22 * cm
DOMAIN_LABELS = {1: "Poor", 2: "Fair", 3: "Good", 4: "Very Good", 5: "Excellent"}


# --------------------------------------------------------------------------------------------- helpers
def _hex(c, fallback):
    try:
        return colors.HexColor(c)
    except Exception:
        return colors.HexColor(fallback)


def _mix(color, k):
    """Mix `color` into white: k=1 is the colour itself, k=0 is white (CSS color-mix(color k%, white))."""
    return colors.Color(1 - (1 - color.red) * k, 1 - (1 - color.green) * k, 1 - (1 - color.blue) * k)


class Palette:
    def __init__(self, rs, accent_color):
        self.accent = _hex(rs.get("accent") or accent_color, "#0b2a6f")
        second = _hex(rs.get("secondary"), "#29a9e0")
        self.line = _mix(second, .62)
        self.tint = _mix(second, .09)
        self.band = _mix(second, .26)
        self.page = _mix(second, .03)
        sky = colors.HexColor("#2b8fd0")
        a = self.accent
        self.label = colors.Color(a.red * .82 + sky.red * .18, a.green * .82 + sky.green * .18, a.blue * .82 + sky.blue * .18)


def _esc(v):
    return str(v if v is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ord(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _img(path, max_h, max_w):
    if not path or not os.path.exists(path):
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            im.load()
            w, h = im.size
        s = min(max_h / h, max_w / w)
        return Image(path, width=w * s, height=h * s)
    except Exception:
        return None


class _Avatar(Flowable):
    """The neutral head-and-shoulders placeholder shown in the passport frame when there is no photo."""
    def __init__(self, w, h, color):
        super().__init__()
        self.w, self.h, self.color = w, h, color

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c = self.canv
        c.setFillColor(self.color)
        c.circle(self.w / 2, self.h * .62, self.w * .2, stroke=0, fill=1)
        p = c.beginPath()
        p.moveTo(self.w * .14, 0)
        p.curveTo(self.w * .14, self.h * .30, self.w * .30, self.h * .38, self.w / 2, self.h * .38)
        p.curveTo(self.w * .70, self.h * .38, self.w * .86, self.h * .30, self.w * .86, 0)
        p.close()
        c.drawPath(p, stroke=0, fill=1)


class SheetFrame(KeepInFrame):
    """One student's sheet, shrunk (never cut) to exactly one page, painted on the sheet's pale background
    with the optional watermark behind the content -- like the on-screen sheet."""
    def __init__(self, maxWidth, maxHeight, content, pal, watermark=None, font="Helvetica-Bold"):
        super().__init__(maxWidth, maxHeight, content, mode="shrink")
        self._pal, self._wm, self._font = pal, watermark, font

    def drawOn(self, canv, x, y, _sW=0):
        canv.saveState()
        canv.setFillColor(self._pal.page)
        canv.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        canv.restoreState()
        if self._wm:
            canv.saveState()
            canv.setFillColor(colors.Color(0, 0, 0, alpha=.05))
            canv.setFont(self._font, 30)
            canv.translate(A4[0] / 2, A4[1] / 2)
            canv.rotate(30)
            words, lines, cur = str(self._wm).split(), [], ""
            for w_ in words:
                t = (cur + " " + w_).strip()
                if canv.stringWidth(t, self._font, 30) > A4[0] * .7 and cur:
                    lines.append(cur)
                    cur = w_
                else:
                    cur = t
            if cur:
                lines.append(cur)
            for i, ln in enumerate(lines):
                canv.drawCentredString(0, -i * 34 + (len(lines) - 1) * 17, ln)
            canv.restoreState()
        super().drawOn(canv, x, y, _sW)


def one_page(elements, pal, watermark=None, font="Helvetica-Bold"):
    return [SheetFrame(W, H, elements, pal, watermark, font)]


# ------------------------------------------------------------------------------------- style factories
class Styles:
    def __init__(self, pal, regular, bold):
        self.pal, self.regular, self.bold = pal, regular, bold

    def p(self, size, color=None, bold=False, align=TA_LEFT, leading=None, name=None):
        return ParagraphStyle(name or f"s{size}{bold}{align}", fontName=self.bold if bold else self.regular, fontSize=size,
                              leading=leading or size * 1.22, textColor=color or self.pal.accent, alignment=align)


def _rounded(rows, widths, pal, bg=None, radius=5, line_w=1.1, pad=(4, 4, 6, 6), valign="MIDDLE", row_heights=None, extra=None):
    t = Table(rows, colWidths=widths, rowHeights=row_heights)
    st = [("BOX", (0, 0), (-1, -1), line_w, pal.line), ("ROUNDEDCORNERS", [radius] * 4), ("VALIGN", (0, 0), (-1, -1), valign),
          ("TOPPADDING", (0, 0), (-1, -1), pad[0]), ("BOTTOMPADDING", (0, 0), (-1, -1), pad[1]),
          ("LEFTPADDING", (0, 0), (-1, -1), pad[2]), ("RIGHTPADDING", (0, 0), (-1, -1), pad[3])]
    if bg is not None:
        st.append(("BACKGROUND", (0, 0), (-1, -1), bg))
    t.setStyle(TableStyle(st + (extra or [])))
    return t


def _row_of(cells, widths, gap=GAP):
    """Lay flowables out side by side with a gap between them (each already a rounded box)."""
    row, cw = [], []
    for i, (c, w) in enumerate(zip(cells, widths)):
        if i:
            row.append("")
            cw.append(gap)
        row.append(c)
        cw.append(w)
    t = Table([row], colWidths=cw)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def banner(text, S):
    return _rounded([[Paragraph(_esc(text).upper(), S.p(12.5, bold=True))]], [W], S.pal, bg=S.pal.band, radius=3, line_w=0, pad=(4.5, 4.5, 8, 8))


def _label_box(label, value, width, S, big=12, value_style=None):
    inner = [Paragraph(_esc(label).upper(), S.p(6.5, color=S.pal.label)), Paragraph(_esc(value) if value not in (None, "") else "&nbsp;", value_style or S.p(big, bold=True, leading=big * 1.2))]
    return _rounded([[inner]], [width], S.pal, bg=S.pal.tint, radius=5, pad=(3, 4, 6, 6), valign="TOP")


# ---------------------------------------------------------------------------------------------- sections
def header(data, term, rs, S, school_name, logo_path, title_override=None, session_line=None):
    pal = S.pal
    layout = rs.get("header_layout")
    logo = _img(rs.get("logo_path") or logo_path, 2.4 * cm, 3.0 * cm) if (rs.get("show_logo", True) and layout != "no-logo") else None
    name = (school_name or rs.get("school_name") or "")
    n_ = len(name)
    fs = 19 if n_ <= 22 else 16 if n_ <= 28 else 14 if n_ <= 34 else 12.5 if n_ <= 40 else 11
    cell = [Paragraph(_esc(name).upper(), S.p(fs, bold=True, align=TA_CENTER, leading=fs * 1.12))]
    if rs.get("tagline"):
        cell.append(Paragraph(_esc(rs["tagline"]), S.p(9, color=pal.label, align=TA_CENTER)))
    if rs.get("contact"):
        cell.append(Paragraph(_esc(rs["contact"]), S.p(9, color=pal.label, align=TA_CENTER)))
    cell.append(Spacer(1, 3))
    cell.append(Paragraph(_esc(title_override or rs.get("title") or "Terminal Report Sheet").upper(), S.p(18, bold=True, align=TA_CENTER, leading=20)))
    if session_line is None:
        parts = [x for x in ((term["session_name"] if rs.get("show_session", True) else None), (term["name"] if rs.get("show_term", True) else None)) if x]
        session_line = " — ".join(parts)
    if session_line:
        cell.append(Paragraph(_esc(session_line), S.p(11, align=TA_CENTER)))
    passport = ""
    if rs.get("show_passport") and data is not None:
        pw, ph = 2.9 * cm, 3.5 * cm
        pimg = _img(rs.get("passport_path"), ph - 4, pw - 4)
        inner = pimg if pimg is not None else _Avatar(pw * .7, ph * .7, _mix(pal.accent, .45))
        passport = _rounded([[inner]], [pw], pal, bg=(colors.white if pimg is not None else pal.band), radius=3, line_w=1.1,
                            pad=(2, 0 if pimg is None else 2, 2, 2), valign="BOTTOM" if pimg is None else "MIDDLE", row_heights=[ph])
    left, right = (logo or ""), passport
    if layout == "logo-right":
        left, right = passport, (logo or "")
    elif layout == "logo-center" and logo is not None:
        cell.insert(0, logo)
        left = ""
    t = Table([[left, cell, right]], colWidths=[3.4 * cm, W - 6.8 * cm, 3.4 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "LEFT"), ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("LINEBELOW", (0, 0), (-1, 0), 1.1, pal.line), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return [t, Spacer(1, 0.25 * cm)]


def id_boxes(items, S):
    """items: [(label, value, is_position)]; four per row, the Class Position box takes the rest of its row."""
    out = []
    base = (W - 3 * GAP) / 4
    for i in range(0, len(items), 4):
        chunk = items[i:i + 4]
        n = len(chunk)
        if n < 4 and chunk[-1][2]:
            widths = [base] * (n - 1) + [W - (n - 1) * (base + GAP)]
        elif n < 4:
            widths = [(W - (n - 1) * GAP) / n] * n
        else:
            widths = [base] * 4
        cells = [_label_box(l, v, w, S) for (l, v, _p), w in zip(chunk, widths)]
        out += [_row_of(cells, widths), Spacer(1, GAP)]
    return out


def _grid_style(pal, rows, header_rows=1, footer_rows=0, size=8.5, fn_reg="Helvetica", fn_bold="Helvetica-Bold"):
    st = [("BOX", (0, 0), (-1, -1), 1.1, pal.line), ("ROUNDEDCORNERS", [5] * 4), ("INNERGRID", (0, 0), (-1, -1), .5, pal.line),
          ("BACKGROUND", (0, 0), (-1, -1), colors.white), ("BACKGROUND", (0, 0), (-1, header_rows - 1), pal.tint),
          ("FONTNAME", (0, 0), (-1, -1), fn_reg), ("FONTNAME", (0, 0), (-1, header_rows - 1), fn_bold), ("FONTSIZE", (0, 0), (-1, -1), size),
          ("TEXTCOLOR", (0, 0), (-1, -1), pal.accent), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    if footer_rows:
        st += [("BACKGROUND", (0, rows - footer_rows), (-1, -1), pal.tint), ("FONTNAME", (0, rows - footer_rows), (-1, -1), fn_bold)]
    return st


def term_table(data, rs, S):
    """Per-term 'Academic Performance' table (same columns, TOTAL / AVERAGE footer as _result_sheet.html)."""
    pal = S.pal
    show_ca3 = data.get("show_ca3")
    div = 4 if show_ca3 else 3
    score = rs.get("show_score", True)
    cols = ["Subject"]
    if score:
        cols += ["CA1", "CA2"] + (["CA3"] if show_ca3 else []) + ["Exam", "Total", "Avg."]
    if rs.get("show_subject_position"):
        cols.append("Pos.")
    if rs.get("show_grade", True):
        cols.append("Grade")
    rem = rs.get("show_remarks", True)
    if rem:
        cols.append("Remark")
    name_style = S.p(9, bold=True)
    rem_style = S.p(8.5, align=TA_CENTER)
    body, written = [cols], []
    for s in data["subjects"]:
        num = isinstance(s.get("total"), (int, float))
        if num:
            written.append(s)
        r = [Paragraph(_esc(s["name"]), name_style)]
        if score:
            r += [str(s["ca1"]), str(s["ca2"])] + ([str(s.get("ca3", "-"))] if show_ca3 else []) + [str(s["exam"]), Paragraph(f"<b>{_esc(s['total'])}</b>", S.p(8.5, align=TA_CENTER)),
                                                                                                   str(round(s["total"] / div, 1) if num else "-")]
        if rs.get("show_subject_position"):
            r.append(str(s.get("position_text", "-")))
        if rs.get("show_grade", True):
            r.append(str(s["grade"]))
        if rem:
            r.append(Paragraph(_esc(s["remark"]), rem_style))
        body.append(r)
    foot = 0
    if score and written:
        def col(k):
            return sum(w[k] for w in written)

        def avg(k):
            return round(col(k) / len(written), 1)
        tot = ["TOTAL", str(col("ca1")), str(col("ca2"))] + ([str(col("ca3"))] if show_ca3 else []) + [str(col("exam")), str(data["total"]), "-"]
        av = ["AVERAGE", str(avg("ca1")), str(avg("ca2"))] + ([str(avg("ca3"))] if show_ca3 else []) + [str(avg("exam")), str(data["average"]), str(round(data["average"] / div, 1))]
        for r in (tot, av):
            for flag in (rs.get("show_subject_position"), rs.get("show_grade", True), rem):
                if flag:
                    r.append("-")
            body.append(r)
        foot = 2
    n = len(cols)
    name_w, rem_w = 4.6 * cm, (3.0 * cm if rem else 0)
    other = max(n - 1 - (1 if rem else 0), 1)
    widths = [name_w] + [(W - name_w - rem_w) / other] * other + ([rem_w] if rem else [])
    t = Table(body, colWidths=widths, repeatRows=1)
    st = _grid_style(pal, len(body), 1, foot, 9, S.regular, S.bold) + [("ALIGN", (0, 0), (0, -1), "LEFT"), ("LEFTPADDING", (0, 0), (0, -1), 7),
                                                                         ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    t.setStyle(TableStyle(st))
    return [Spacer(1, 5), banner("Academic Performance", S), Spacer(1, 3), t]


def cumulative_table(cum, S):
    """Cumulative / Annual Performance: fixed column widths computed from the term count (same formula as
    _cumulative_breakdown.html), so the table is ALWAYS exactly the page width and Remark is never cut off."""
    pal = S.pal
    ca3 = bool(cum.get("show_ca3"))
    terms = list(cum["terms"])
    per = 7 if ca3 else 6
    # columns per term: CA1 CA2 [CA3] Exam Total Avg. Pos.  (HTML shows 7 with CA3 / 6 without -> Avg and Pos both present)
    nt = len(terms)
    term_cols = nt * per
    overall_pct = 25.6
    col_pct = max(2.4, min(5.6, (100 - overall_pct - 10.5) / term_cols))
    subj_pct = 100 - overall_pct - term_cols * col_pct
    pt = W / 100.0
    widths = [subj_pct * pt] + [col_pct * pt] * term_cols + [4.8 * pt, 5.6 * pt, 3.8 * pt, 4.0 * pt, 7.4 * pt]
    fs = max(4.9, min(7.0, (col_pct * pt - 1.6) / 2.9))
    div = 4 if ca3 else 3
    sty_n = S.p(fs, align=TA_CENTER, leading=fs * 1.2)
    sty_b = S.p(fs, bold=True, align=TA_CENTER, leading=fs * 1.2)
    sty_subj = S.p(min(8, fs + 1), bold=True, leading=(fs + 1) * 1.2)
    sty_rem = S.p(max(4.8, fs - .3), align=TA_CENTER, leading=fs * 1.2)

    sub = ["CA1", "CA2"] + (["CA3"] if ca3 else []) + ["Exam", "Total", "Avg.", "Pos."]
    head0 = ["Subject"]
    for tn in terms:
        head0 += [str(tn)] + [""] * (per - 1)
    head0 += ["Overall Cumulative", "", "", "", ""]
    head1 = [""] + sub * nt + ["Total", "Average", "Pos.", "Grade", "Remark"]
    body = [head0, head1]
    for name, s in cum["by_subject"].items():
        r = [Paragraph(_esc(name), sty_subj)]
        for i, c in enumerate(s["term_components"]):
            if c:
                pos = s["term_positions"][i] if i < len(s["term_positions"]) else None
                tot = c.get("total")
                r += [str(c["ca1"] if c.get("ca1") is not None else "-"), str(c["ca2"] if c.get("ca2") is not None else "-")]
                if ca3:
                    r.append(str(c["ca3"] if c.get("ca3") is not None else "-"))
                r += [str(c["exam"] if c.get("exam") is not None else "-"), Paragraph(f"<b>{_esc(tot)}</b>", sty_n),
                      str(round(tot / div, 1)) if isinstance(tot, (int, float)) else "-", _ord(pos) if pos is not None else "-"]
            else:
                r += ["-"] * per
        r += [Paragraph(f"<b>{_esc(s['cum_total'] if s.get('cum_total') is not None else '-')}</b>", sty_n), str(s.get("average", "-")),
              _ord(s["position"]) if s.get("position") is not None else "-", str(s.get("grade", "-")), Paragraph(_esc(s.get("remark", "")), sty_rem)]
        body.append(r)

    def foot(label, per_term, overall):
        r = [label]
        for x in per_term:
            if x:
                r += [str(x["ca1"]), str(x["ca2"])] + ([str(x["ca3"])] if ca3 else []) + [str(x["exam"]), str(x["total"]), "-", "-"]
            else:
                r += ["-"] * per
        r += [str(overall if overall is not None else "-"), "", "", "", ""]
        return r
    body.append(foot("TOTAL", cum.get("term_totals") or [None] * nt, cum.get("cum_grand_total")))
    body.append(foot("AVERAGE", cum.get("term_averages") or [None] * nt, cum.get("cum_grand_average")))

    n = len(body)
    t = Table(body, colWidths=widths, repeatRows=2)
    st = _grid_style(pal, n, 2, 2, fs, S.regular, S.bold)
    st += [("SPAN", (0, 0), (0, 1)), ("ALIGN", (0, 0), (0, -1), "LEFT"), ("LEFTPADDING", (0, 0), (0, -1), 4), ("FONTSIZE", (0, 0), (0, 1), 8.5),
           ("LEFTPADDING", (1, 0), (-1, -1), 1), ("RIGHTPADDING", (1, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (0, -1), 2),
           ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
           ("FONTSIZE", (1, 0), (-1, 0), 8.5), ("FONTSIZE", (1, 1), (-1, 1), max(4.6, fs - .7))]
    for i in range(nt):
        a = 1 + i * per
        st.append(("SPAN", (a, 0), (a + per - 1, 0)))
    o = 1 + term_cols
    st += [("SPAN", (o, 0), (o + 4, 0)), ("SPAN", (o + 1, n - 2), (o + 4, n - 2)), ("SPAN", (o + 1, n - 1), (o + 4, n - 1))]
    t.setStyle(TableStyle(st))
    return [Spacer(1, 5), banner("Cumulative / Annual Performance", S), Spacer(1, 3), t]


def summary_strip(cells, S):
    pal = S.pal
    lab = [Paragraph(_esc(l), S.p(9, bold=True, align=TA_CENTER)) for l, _v in cells]
    val = [Paragraph(_esc(v), S.p(14.5, bold=True, align=TA_CENTER, leading=17)) for _l, v in cells]
    t = Table([lab, val], colWidths=[W / len(cells)] * len(cells))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.1, pal.line), ("ROUNDEDCORNERS", [5] * 4), ("BACKGROUND", (0, 0), (-1, -1), pal.tint),
                           ("LINEBELOW", (0, 0), (-1, 0), .6, pal.line), ("LINEBEFORE", (1, 0), (-1, -1), .6, pal.line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, 0), (-1, 0), 5), ("TOPPADDING", (0, 1), (-1, 1), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 8)]))
    return [Spacer(1, 6), banner("Academic Performance Summary", S), Spacer(1, 3), t]


def domain_tables(groups, S):
    pal = S.pal
    hw = (W - GAP * 2) / 2
    tables = []
    for g in groups:
        rows = [[Paragraph(_esc(g["label"]), S.p(10.5, bold=True)), Paragraph("Rating", S.p(10.5, bold=True, align=TA_CENTER))]]
        for n, v in g["items"]:
            rows.append([Paragraph(_esc(n), S.p(9.5)), Paragraph(f"<b>{_esc(v)}</b>", S.p(9.5, align=TA_CENTER))])
        t = Table(rows, colWidths=[hw * .66, hw * .34])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.1, pal.line), ("ROUNDEDCORNERS", [5] * 4), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                               ("BACKGROUND", (0, 0), (-1, 0), pal.tint), ("LINEBELOW", (0, 0), (-1, -2), .5, pal.line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6), ("LEFTPADDING", (0, 0), (0, -1), 7)]))
        tables.append(t)
    out = [Spacer(1, 3), banner("Domain Ratings", S), Spacer(1, 3)]
    for i in range(0, len(tables), 2):
        pair = tables[i:i + 2]
        out += [_row_of(pair, [hw] * len(pair)), Spacer(1, GAP)]
    return out


def attendance(items, S):
    """items: [(label, value, weight)]"""
    total_w = sum(w for _l, _v, w in items)
    avail = W - GAP * (len(items) - 1)
    widths = [avail * w / total_w for _l, _v, w in items]
    cells = [_label_box(l, v if v is not None else "—", wd, S, big=12) for (l, v, _w), wd in zip(items, widths)]
    return [Spacer(1, 2), _row_of(cells, widths), Spacer(1, GAP)]


def comments(items, S):
    wd = (W - GAP * (len(items) - 1)) / len(items)
    cells = []
    for label, text in items:
        body = Paragraph((_esc(text).replace("\n", "<br/>")) or "&nbsp;", S.p(10.5, leading=13))
        cells.append(_rounded([[[Paragraph(_esc(label).upper(), S.p(7.5, color=S.pal.label)), body]]], [wd], S.pal, bg=S.pal.tint, radius=5, pad=(3, 5, 6, 6), valign="TOP",
                              row_heights=[1.9 * cm]))
    return [_row_of(cells, [wd] * len(cells)), Spacer(1, 6)]


def signatures(cells, S):
    """cells: [(role, sig_path, name, show_sig, show_date, date_iso)] -- ONE line above the name."""
    pal = S.pal
    built = []
    for role, sig, name, show_sig, show_date, date_iso in cells:
        rows, st = [], []
        if show_sig:
            simg = _img(sig, 1.1 * cm, 4 * cm) if sig else None
            rows.append([simg if simg is not None else Spacer(1, 1.1 * cm)])
            st.append(("LINEBELOW", (0, 0), (0, 0), 1.1, pal.accent))
            rows.append([Paragraph(f"{_esc(role)}{(': ' + _esc(name)) if name else ''}", S.p(10, align=TA_CENTER))])
        if show_date:
            rows.append([Paragraph(f"Date: {format_dmy(date_iso) if date_iso else ''}", S.p(10, align=TA_CENTER))])
        t = Table(rows, colWidths=[7.6 * cm])
        t.setStyle(TableStyle(st + [("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        built.append(t)
    hw = W / 2
    row = Table([[b for b in built] + [""] * (2 - len(built))], colWidths=[hw, hw])
    row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return [Spacer(1, 0.3 * cm), row]


def keys(grading, domain_key_on, S):
    pal = S.pal
    left = right = None
    if grading:
        items = [Paragraph(f"{_esc(g['grade'])} = {g['min_score']:g} – {g['max_score']:g} ({_esc(g['remark'])})", S.p(7)) for g in grading]
        rows = [items[i:i + 3] + [""] * (3 - len(items[i:i + 3])) for i in range(0, len(items), 3)]
        inner = Table(rows, colWidths=[3.8 * cm] * 3)
        inner.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        left = [Paragraph("GRADING SCALE", S.p(8, bold=True)), inner]
    if domain_key_on:
        txt = " &nbsp;".join(f"{k}&nbsp;=&nbsp;{v.replace(' ', '&nbsp;')}" for k, v in DOMAIN_LABELS.items())
        right = [Paragraph("DOMAIN RATINGS SCALE", S.p(8, bold=True)), Paragraph(txt, S.p(7, leading=10))]
    if not left and not right:
        return []
    if left and right:
        t = Table([[left, right]], colWidths=[11.4 * cm, W - 11.4 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBEFORE", (1, 0), (1, 0), .6, pal.line), ("LEFTPADDING", (1, 0), (1, 0), 10),
                               ("LEFTPADDING", (0, 0), (0, 0), 0), ("LINEABOVE", (0, 0), (-1, 0), 1.1, pal.line), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    else:
        t = Table([[left or right]], colWidths=[W])
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEABOVE", (0, 0), (-1, 0), 1.1, pal.line), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return [Spacer(1, 0.25 * cm), t]


# ---------------------------------------------------------------------------------------- full sheets
def result_elements(data, term, school_name, logo_path, student_full_name, styles, accent_color="#0b2a6f",
                    teacher_signature=None, principal_signature=None, regular="Helvetica", bold="Helvetica-Bold"):
    """The terminal result (per-term, or Cumulative/Annual when that state is on) as flowables."""
    rs = data.get("rs") or {}
    info = data.get("info") or {}
    student, class_row = data["student"], data["class_row"]
    pal = Palette(rs, accent_color)
    S = Styles(pal, regular, bold)
    cum = data.get("cumulative")
    show_cum = bool(cum and cum.get("terms"))
    name = student_full_name(student) if student_full_name else f"{student['last_name']} {student['first_name']}"
    els = []
    els += header(data, term, rs, S, school_name, logo_path)

    ids = [("Name", name, False)]
    if rs.get("show_admission_no", True):
        ids.append(("Admission No.", student["admission_no"], False))
    if rs.get("show_class", True):
        ids.append(("Class / Arm", class_row["name"], False))
    if rs.get("show_session", True):
        ids.append(("Academic Session", term["session_name"], False))
    if rs.get("show_term", True):
        ids.append(("Term", term["name"], False))
    if rs.get("show_overall_position", True):
        pos = data.get("position")
        ps = str(pos) if pos is not None else "-"
        if data.get("class_size"):
            ps += f" / {data['class_size']}"
        ids.append(("Class Position", ps, True))
    els += id_boxes(ids, S)

    if show_cum:
        els += cumulative_table(cum, S)
        cs = data.get("cum_summary") or {}
        mx = cs.get("max_each")
        pct = round(cs["average"] / mx * 100, 1) if cs.get("average") and mx else 0
        cells = [("Total Subjects", cs.get("subjects_written", "-")), ("Total Score", cs.get("total") if cs.get("total") is not None else "-"),
                 ("Average Score", cs.get("average", "-")), ("Percentage", f"{pct}%"), ("Grade", cs.get("grade", "-")), ("Remark", cs.get("remark", "-"))]
    else:
        els += term_table(data, rs, S)
        tob = data.get("total_obtainable")
        pct = round(data["total"] / tob * 100, 1) if tob else 0
        cells = [("Total Subjects", data.get("subjects_written", "-")), ("Total Score", data["total"]), ("Average Score", data["average"]),
                 ("Percentage", f"{pct}%"), ("Grade", data.get("overall_grade", "-")), ("Remark", data.get("overall_remark", "-"))]
    els += summary_strip([(l, "-" if v is None else v) for l, v in cells], S)

    groups = data.get("domain_groups") if rs.get("show_domains", True) else None
    if groups:
        els += domain_tables(groups, S)

    promo = data.get("promotion_status") if rs.get("show_promotion", True) else None
    att = []
    if rs.get("show_attendance", True):
        for flag, label, key in (("show_days_opened", "Days School Opened", "days_school_opened"), ("show_days_present", "Days Present", "days_present"),
                                 ("show_days_absent", "Days Absent", "days_absent"), ("show_days_late", "Days Late", "days_late")):
            if rs.get(flag, True):
                att.append((label, info.get(key), 1))
    if promo:
        att.append(("Promotion Status", promo, 2.4))
    if att:
        els += attendance(att, S)

    cm_items = []
    if rs.get("show_teacher_comment", True):
        cm_items.append(("Class/Form Teacher's Comment", info.get("teacher_comment")))
    if rs.get("show_principal_comment", True):
        cm_items.append(("Principal's Comment", info.get("principal_comment")))
    if cm_items:
        els += comments(cm_items, S)

    sg = []
    if rs.get("show_teacher_signature", True) or rs.get("show_teacher_sign_date", True):
        sg.append(("Class Teacher", (teacher_signature or {}).get("path"), data.get("teacher_name"), rs.get("show_teacher_signature", True),
                   rs.get("show_teacher_sign_date", True), info.get("teacher_signed_date")))
    if rs.get("show_principal_signature", True) or rs.get("show_principal_sign_date", True):
        sg.append(("Principal", (principal_signature or {}).get("path"), data.get("principal_name"), rs.get("show_principal_signature", True),
                   rs.get("show_principal_sign_date", True), info.get("principal_signed_date")))
    if sg:
        els += signatures(sg, S)

    if rs.get("next_term_resumes"):
        els += [Spacer(1, 4), Paragraph(f"Next Term Resumes: <b>{_esc(rs['next_term_resumes'])}</b>", S.p(9))]
    scale = (rs.get("grading_scale") or []) if rs.get("show_grading_key", True) else []
    els += keys(scale, bool(groups), S)
    if rs.get("footer"):
        els += [Spacer(1, 4), Paragraph(_esc(rs["footer"]), S.p(8))]
    return els, pal, rs.get("watermark")


def cumulative_page_elements(data, session, school_name, logo_path, student_full_name, rs, accent_color="#0b2a6f", regular="Helvetica", bold="Helvetica-Bold"):
    """The dedicated Annual / Cumulative Result page (cumulative_result_print.html) as flowables."""
    rs = rs or {}
    pal = Palette(rs, accent_color)
    S = Styles(pal, regular, bold)
    student, class_row = data["student"], data["class_row"]
    name = student_full_name(student) if student_full_name else f"{student['last_name']} {student['first_name']}"
    sess_name = session["name"] if session is not None else ""
    els = header(None, None, rs, S, school_name, logo_path, title_override="Annual / Cumulative Result", session_line=sess_name)
    ids = [("Name", name, False), ("Admission / Register No.", student["admission_no"], False), ("Class / Arm", class_row["name"], False)]
    if class_row["category"] if "category" in class_row.keys() else None:
        ids.append(("Category", class_row["category"], False))
    ids += [("Cumulative Average", data.get("average", "-"), False), ("Grade", f"{data.get('grade', '-')} ({data.get('remark', '')})", False)]
    pos = data.get("position")
    ids.append(("Overall Position", f"{pos}" + (f" of {data['class_size']}" if data.get("class_size") else ""), True))
    els += id_boxes(ids, S)
    cum = data.get("cumulative")
    if cum and cum.get("terms"):
        els += cumulative_table(cum, S)
    if rs.get("footer"):
        els += [Spacer(1, 4), Paragraph(_esc(rs["footer"]), S.p(8))]
    return els, pal, rs.get("watermark")
