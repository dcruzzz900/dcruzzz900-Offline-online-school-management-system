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
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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
        self.second = second
        self.solid = colors.Color(second.red * .72 + a.red * .28, second.green * .72 + a.green * .28, second.blue * .72 + a.blue * .28)
        self.gray = colors.HexColor("#eef2f6")
        self.soft_white = colors.Color(1, 1, 1, alpha=.2)


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
    def __init__(self, maxWidth, maxHeight, content, pal, watermark=None, font="Helvetica-Bold", page_color=None):
        super().__init__(maxWidth, maxHeight, content, mode="shrink")
        self._pal, self._wm, self._font = pal, watermark, font
        self._page = page_color if page_color is not None else pal.page

    def drawOn(self, canv, x, y, _sW=0):
        canv.saveState()
        canv.setFillColor(self._page)
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


def one_page(elements, pal, watermark=None, font="Helvetica-Bold", page_color=None):
    return [SheetFrame(W, H, elements, pal, watermark, font, page_color)]


# ------------------------------------------------------------------------------------- style factories
# V101: the six selectable designs, as the fallback renderer sees them (mirrors result-sheet.css).
#   hdr: plain | band (solid colour header);  halign: default header text alignment (the school's own
#   "Header text alignment" setting always wins);  idm: how the identity details are laid out;  banner: section title
#   style;  th: table heading style;  zebra: striped rows;  box: shape of the small detail boxes;  summ: key-figure
#   style;  layout: linear | sidebar | cards;  page: page background.
STYLES = {
    "professional_classic": dict(hdr="plain", halign="center", idm="boxes", banner="band", th="tint", zebra=False, box="rounded", summ="grid", layout="linear", page="tint"),
    "executive": dict(hdr="band", halign="center", idm="ruled", banner="rule", th="solid", zebra=True, box="bar", summ="topbar", layout="linear", page="white"),
    "minimal_line": dict(hdr="plain", halign="left", idm="strip", banner="line", th="plain", zebra=False, box="line", summ="plain", layout="linear", page="white"),
    "sidebar_profile": dict(hdr="plain", halign="left", idm="stack", banner="band", th="tint", zebra=False, box="rounded", summ="grid", layout="sidebar", page="white"),
    "dashboard_cards": dict(hdr="plain", halign="left", idm="strip", banner="plain", th="tint", zebra=False, box="card", summ="topbar", layout="cards", page="gray"),
    "bold_banner": dict(hdr="band", halign="center", idm="chips", banner="pill", th="solid", zebra=True, box="pill", summ="tiles", layout="linear", page="white"),
}


class Styles:
    def __init__(self, pal, regular, bold, key="professional_classic"):
        self.pal, self.regular, self.bold = pal, regular, bold
        self.key = key if key in STYLES else "professional_classic"
        self.m = STYLES[self.key]

    def p(self, size, color=None, bold=False, align=TA_LEFT, leading=None, name=None):
        return ParagraphStyle(name or f"s{size}{bold}{align}", fontName=self.bold if bold else self.regular, fontSize=size,
                              leading=leading or size * 1.22, textColor=color or self.pal.accent, alignment=align)


class _Cover(Flowable):
    """A photo drawn to FILL its frame (cropped to cover, top-centred so faces stay in), no border. Optionally round."""
    def __init__(self, path, w, h, radius=3, circle=False):
        super().__init__()
        self.path, self.w, self.h, self.radius, self.circle = path, w, h, radius, circle

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        from PIL import Image as PILImage
        from reportlab.lib.utils import ImageReader
        c = self.canv
        try:
            with PILImage.open(self.path) as im:
                iw, ih = im.size
            c.saveState()
            p = c.beginPath()
            if self.circle:
                p.ellipse(0, 0, self.w, self.h)
            else:
                p.roundRect(0, 0, self.w, self.h, self.radius)
            c.clipPath(p, stroke=0, fill=0)
            k = max(self.w / iw, self.h / ih)
            dw, dh = iw * k, ih * k
            c.drawImage(ImageReader(self.path), (self.w - dw) / 2, self.h - dh, dw, dh, mask="auto")
            c.restoreState()
        except Exception:
            pass


def _pad_style(p, pad):
    return [("TOPPADDING", (0, 0), (-1, -1), pad[0]), ("BOTTOMPADDING", (0, 0), (-1, -1), pad[1]),
            ("LEFTPADDING", (0, 0), (-1, -1), pad[2]), ("RIGHTPADDING", (0, 0), (-1, -1), pad[3])]


def _rounded(rows, widths, pal, bg=None, radius=5, line_w=1.1, pad=(4, 4, 6, 6), valign="MIDDLE", row_heights=None, extra=None):
    t = Table(rows, colWidths=widths, rowHeights=row_heights)
    st = [("VALIGN", (0, 0), (-1, -1), valign)] + _pad_style(None, pad)
    if line_w:
        st += [("BOX", (0, 0), (-1, -1), line_w, pal.line)]
    if radius:
        st.append(("ROUNDEDCORNERS", [radius] * 4))
    if bg is not None:
        st.append(("BACKGROUND", (0, 0), (-1, -1), bg))
    t.setStyle(TableStyle(st + (extra or [])))
    return t


def _box(rows, widths, S, pad=(3, 4, 6, 6), valign="TOP", row_heights=None):
    """A small detail box, shaped by the chosen design (rounded / left bar / top line / card / pill)."""
    pal, kind = S.pal, S.m["box"]
    if kind == "bar":
        return _rounded(rows, widths, pal, bg=pal.tint, radius=0, line_w=0, pad=pad, valign=valign, row_heights=row_heights,
                        extra=[("LINEBEFORE", (0, 0), (0, -1), 3.4, pal.second)])
    if kind == "line":
        return _rounded(rows, widths, pal, bg=None, radius=0, line_w=0, pad=(pad[0], pad[1], 0, pad[3]), valign=valign, row_heights=row_heights,
                        extra=[("LINEABOVE", (0, 0), (-1, 0), .6, pal.line)])
    if kind == "card":
        return _rounded(rows, widths, pal, bg=colors.white, radius=6, line_w=.6, pad=pad, valign=valign, row_heights=row_heights)
    if kind == "pill":
        return _rounded(rows, widths, pal, bg=pal.band, radius=10, line_w=0, pad=(pad[0] + 1, pad[1] + 1, pad[2] + 2, pad[3]), valign=valign, row_heights=row_heights)
    return _rounded(rows, widths, pal, bg=pal.tint, radius=5, pad=pad, valign=valign, row_heights=row_heights)


def _row_of(cells, widths, gap=GAP):
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


def _card(flowables, w, S, top_bar=False):
    """Dashboard-cards design: a white rounded card around a group of flowables."""
    extra = [("LINEABOVE", (0, 0), (-1, 0), 4, S.pal.accent)] if top_bar else []
    return _rounded([[flowables]], [w], S.pal, bg=colors.white, radius=7, line_w=.5, pad=(6, 6, 8, 8), valign="TOP", extra=extra)


# ---------------------------------------------------------------------------------------------- sections
def banner(text, S, w=None):
    w = w or W
    pal, kind = S.pal, S.m["banner"]
    txt = _esc(text).upper()
    if kind == "rule":
        t = Table([["", Paragraph(txt, S.p(12, bold=True))]], colWidths=[9, w - 9])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), pal.second), ("LINEBELOW", (0, 0), (-1, 0), 1.8, pal.accent), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LEFTPADDING", (1, 0), (1, 0), 7), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0)]))
        return t
    if kind == "line":
        t = Table([[Paragraph(txt.replace("", " ").strip() if False else txt, S.p(8.2, bold=True, leading=10))]], colWidths=[w])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), .6, pal.line), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t
    if kind == "plain":
        t = Table([[Paragraph(_esc(text), S.p(11, bold=True))]], colWidths=[w])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), .6, pal.line), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t
    if kind == "pill":
        from reportlab.pdfbase.pdfmetrics import stringWidth
        tw = stringWidth(txt, S.bold, 9) + 22
        t = Table([[Paragraph(txt, S.p(9, color=colors.white, bold=True, leading=11))]], colWidths=[min(tw, w)], hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), pal.accent), ("ROUNDEDCORNERS", [9] * 4), ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                               ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2)]))
        return t
    return _rounded([[Paragraph(txt, S.p(12.5 if w == W else 9.5, bold=True))]], [w], pal, bg=pal.band, radius=3, line_w=0, pad=(4.5, 4.5, 8, 8))


def _label_box(label, value, width, S, big=12, value_style=None, inline=False):
    inner = [Paragraph(_esc(label).upper(), S.p(6.5, color=S.pal.label)), Paragraph(_esc(value) if value not in (None, "") else "&nbsp;", value_style or S.p(big, bold=True, leading=big * 1.2))]
    return _box([[inner]], [width], S, pad=(3, 4, 6, 6), valign="TOP")


def _logo_cell(rs, logo_path, layout):
    return _img(rs.get("logo_path") or logo_path, 2.4 * cm, 3.0 * cm) if (rs.get("show_logo", True) and layout != "no-logo") else None


def header(data, term, rs, S, school_name, logo_path, title_override=None, session_line=None, w=None):
    w = w or W
    pal, m = S.pal, S.m
    layout = rs.get("header_layout")
    logo = _logo_cell(rs, logo_path, layout)
    band = m["hdr"] == "band"
    tc = colors.white if band else None
    sub = colors.Color(1, 1, 1, alpha=.85) if band else pal.label
    al = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}.get(rs.get("text_align") or "", {"left": TA_LEFT, "center": TA_CENTER}[m["halign"]])
    name = (school_name or rs.get("school_name") or "")
    n_ = len(name)
    fs = 19 if n_ <= 22 else 16 if n_ <= 28 else 14 if n_ <= 34 else 12.5 if n_ <= 40 else 11
    if S.key == "minimal_line":
        fs = min(fs, 12)
    cell = [Paragraph(_esc(name).upper(), S.p(fs, color=tc, bold=True, align=al, leading=fs * 1.12))]
    if rs.get("tagline"):
        cell.append(Paragraph(_esc(rs["tagline"]), S.p(9, color=sub, align=al)))
    if rs.get("contact"):
        cell.append(Paragraph(_esc(rs["contact"]), S.p(9, color=sub, align=al)))
    cell.append(Spacer(1, 3))
    ttl = _esc(title_override or rs.get("title") or "Terminal Report Sheet")
    if S.key == "minimal_line":
        cell.append(Paragraph(ttl, S.p(23, color=tc, align=al, leading=25)))
    else:
        cell.append(Paragraph(ttl.upper(), S.p(18 if S.key not in ("executive", "sidebar_profile") else 15, color=tc, bold=True, align=al, leading=20)))
    if session_line is None:
        parts = [x for x in ((term["session_name"] if rs.get("show_session", True) else None), (term["name"] if rs.get("show_term", True) else None)) if x]
        session_line = " — ".join(parts)
    if session_line:
        cell.append(Paragraph(_esc(session_line), S.p(11 if S.key != "minimal_line" else 9.5, color=tc, align=al)))
    passport = ""
    if rs.get("show_passport") and data is not None:
        circle = S.key == "bold_banner"
        pw, ph = (3.2 * cm, 3.2 * cm) if circle else (2.9 * cm, 3.5 * cm)
        radius = 0 if S.key == "minimal_line" else 3
        bgc = pal.soft_white if band else pal.band
        if rs.get("passport_path") and os.path.exists(rs.get("passport_path")):
            inner = _Cover(rs["passport_path"], pw, ph, radius=radius, circle=circle)
            passport = Table([[inner]], colWidths=[pw], rowHeights=[ph])
            passport.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        else:
            inner = _Avatar(pw * .7, ph * .7, _mix(pal.accent, .45) if not band else colors.Color(1, 1, 1, alpha=.55))
            passport = Table([[inner]], colWidths=[pw], rowHeights=[ph])
            passport.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bgc), ("ROUNDEDCORNERS", [pw / 2] * 4 if circle else [radius] * 4), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                          ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    left, right = (logo or ""), passport
    if layout == "logo-right":
        left, right = passport, (logo or "")
    elif layout == "logo-center" and logo is not None:
        cell.insert(0, logo)
        left = ""
    t = Table([[left, cell, right]], colWidths=[3.4 * cm, w - 6.8 * cm, 3.4 * cm])
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "LEFT"), ("ALIGN", (2, 0), (2, 0), "RIGHT"),
          ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
    if band:
        grad = pal.accent if S.key == "executive" else _mix(pal.accent, 1)
        st += [("BACKGROUND", (0, 0), (-1, -1), grad), ("ROUNDEDCORNERS", [8] * 4), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
               ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]
        if S.key == "executive":
            st.append(("LINEBELOW", (0, 0), (-1, 0), 3.4, pal.second))
    elif S.key == "dashboard_cards":
        st += [("BACKGROUND", (0, 0), (-1, -1), colors.white), ("ROUNDEDCORNERS", [7] * 4), ("LINEABOVE", (0, 0), (-1, 0), 4, pal.accent), ("LEFTPADDING", (0, 0), (-1, -1), 10),
               ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
    elif S.key == "minimal_line":
        st.append(("LINEBELOW", (0, 0), (-1, 0), 1, pal.accent))
    else:
        st.append(("LINEBELOW", (0, 0), (-1, 0), 1.1 if S.key != "sidebar_profile" else 3.4, pal.line if S.key != "sidebar_profile" else pal.accent))
    t.setStyle(TableStyle(st))
    return [t, Spacer(1, 0.25 * cm)]


def id_boxes(items, S, w=None):
    """items: [(label, value, is_position)]. Layout follows the chosen design."""
    w = w or W
    pal, kind = S.pal, S.m["idm"]
    if kind == "stack":
        out = []
        for l, v, _p in items:
            out += [_box([[[Paragraph(_esc(l).upper(), S.p(6.2, color=pal.label)), Paragraph(_esc(v) or "&nbsp;", S.p(9.5, bold=True, leading=11))]]], [w], S,
                         pad=(2, 3, 5, 5)) if False else _rounded([[[Paragraph(_esc(l).upper(), S.p(6.2, color=pal.label)), Paragraph(_esc(v) or "&nbsp;", S.p(9.5, bold=True, leading=11))]]],
                                                                   [w], pal, bg=colors.white, radius=3, line_w=0, pad=(2, 3, 6, 5), valign="TOP", extra=[("LINEBEFORE", (0, 0), (0, -1), 3.2, pal.accent)]), Spacer(1, 4)]
        return out
    if kind == "ruled":
        per = 3
        rows = []
        for i in range(0, len(items), per):
            ch = items[i:i + per]
            r = []
            for l, v, _p in ch:
                r += [Paragraph(_esc(l), S.p(8.5, color=_mix(pal.accent, .65))), Paragraph(_esc(v), S.p(10.5, bold=True, align=TA_RIGHT))]
            r += [""] * (2 * per - len(r))
            rows.append(r)
        cw = []
        for _ in range(per):
            cw += [(w / per) * .34, (w / per) * .66]
        t = Table(rows, colWidths=[c for c in cw])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (1, -1), .6, pal.line), ("LINEBELOW", (2, 0), (3, -1), .6, pal.line), ("LINEBELOW", (4, 0), (5, -1), .6, pal.line),
                               ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (1, 0), (1, -1), 12), ("RIGHTPADDING", (3, 0), (3, -1), 12), ("LEFTPADDING", (2, 0), (2, -1), 0), ("LEFTPADDING", (4, 0), (4, -1), 0)]))
        return [t, Spacer(1, 6)]
    if kind == "chips":
        from reportlab.pdfbase.pdfmetrics import stringWidth
        rows, cur, curw = [], [], 0
        sized = []
        for l, v, _p in items:
            tw = stringWidth(str(l).upper(), S.regular, 6.5) + stringWidth(str(v), S.bold, 10) + 26
            sized.append((l, v, tw))
        for l, v, tw in sized:
            if cur and curw + tw + 5 > w:
                rows.append(cur); cur, curw = [], 0
            cur.append((l, v, tw)); curw += tw + 5
        if cur:
            rows.append(cur)
        out = []
        for r in rows:
            cells = [_rounded([[Paragraph(f'<font size="6.5" color="#{pal.label.hexval()[2:]}">{_esc(l).upper()}</font>&nbsp;&nbsp;<b>{_esc(v)}</b>', S.p(10, leading=12))]], [tw], pal, bg=pal.band, radius=10,
                              line_w=0, pad=(3, 3, 10, 8)) for l, v, tw in r]
            out += [_row_of(cells, [c[2] for c in r], gap=5), Spacer(1, 4)]
        return out
    if kind == "strip":
        per = 6 if S.key == "minimal_line" else 4
        out = []
        for i in range(0, len(items), per):
            ch = items[i:i + per]
            cells = [[Paragraph(_esc(l).upper(), S.p(6.2, color=pal.label)), Paragraph(_esc(v) or "&nbsp;", S.p(10.5, bold=True, leading=12))] for l, v, _p in ch]
            wd = (w - 8) / len(ch) if len(ch) == per else (w - 8) / per
            t = Table([cells], colWidths=[wd] * len(ch))
            st = [("LINEBEFORE", (1, 0), (-1, 0), .6, pal.line), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                  ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
            if S.key == "minimal_line":
                st += [("LEFTPADDING", (0, 0), (0, 0), 0), ("LINEBELOW", (0, 0), (-1, 0), .6, pal.line)] if i + per >= len(items) else [("LEFTPADDING", (0, 0), (0, 0), 0)]
            else:
                st += [("BACKGROUND", (0, 0), (-1, -1), colors.white), ("ROUNDEDCORNERS", [7] * 4), ("BOX", (0, 0), (-1, -1), .5, pal.line)]
            t.setStyle(TableStyle(st))
            out += [t, Spacer(1, 4)]
        return out
    out = []
    base = (w - 3 * GAP) / 4
    for i in range(0, len(items), 4):
        chunk = items[i:i + 4]
        n = len(chunk)
        if n < 4 and chunk[-1][2]:
            widths = [base] * (n - 1) + [w - (n - 1) * (base + GAP)]
        elif n < 4:
            widths = [(w - (n - 1) * GAP) / n] * n
        else:
            widths = [base] * 4
        cells = [_label_box(l, v, wd, S) for (l, v, _p), wd in zip(chunk, widths)]
        out += [_row_of(cells, widths), Spacer(1, GAP)]
    return out


def _grid_style(pal, rows, header_rows=1, footer_rows=0, size=8.5, fn_reg="Helvetica", fn_bold="Helvetica-Bold", S=None):
    th = S.m["th"] if S else "tint"
    zebra = S.m["zebra"] if S else False
    rounded = (S is None) or S.m["box"] != "line"
    st = [("BOX", (0, 0), (-1, -1), 1.1, pal.line), ("INNERGRID", (0, 0), (-1, -1), .5, pal.line),
          ("BACKGROUND", (0, 0), (-1, -1), colors.white), ("FONTNAME", (0, 0), (-1, -1), fn_reg), ("FONTNAME", (0, 0), (-1, header_rows - 1), fn_bold),
          ("FONTSIZE", (0, 0), (-1, -1), size), ("TEXTCOLOR", (0, 0), (-1, -1), pal.accent), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    if rounded:
        st.append(("ROUNDEDCORNERS", [5] * 4 if S is None or S.m["box"] != "bar" else [0] * 4))
    if th == "solid":
        hc = pal.accent if S.key == "executive" else pal.solid
        st += [("BACKGROUND", (0, 0), (-1, header_rows - 1), hc), ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white)]
    elif th == "plain":
        st = [x for x in st if x[0] not in ("BOX", "INNERGRID")] + [("LINEBELOW", (0, 0), (-1, header_rows - 1), 1.1, pal.accent), ("LINEBELOW", (0, header_rows), (-1, -2), .4, pal.line)]
    else:
        st.append(("BACKGROUND", (0, 0), (-1, header_rows - 1), pal.tint))
    if zebra and rows - header_rows - footer_rows > 1:
        for r in range(header_rows + 1, rows - footer_rows, 2):
            st.append(("BACKGROUND", (0, r), (-1, r), pal.tint))
    if footer_rows:
        st += [("BACKGROUND", (0, rows - footer_rows), (-1, -1), pal.tint if th != "plain" else colors.white), ("FONTNAME", (0, rows - footer_rows), (-1, -1), fn_bold)]
        if th == "plain":
            st.append(("LINEABOVE", (0, rows - footer_rows), (-1, rows - footer_rows), 1.1, pal.accent))
    return st


def term_table(data, rs, S, w=None):
    w = w or W
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
            return sum(x[k] for x in written)

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
    name_w, rem_w = (4.6 * cm if w == W else 3.2 * cm), ((3.0 * cm if w == W else 2.4 * cm) if rem else 0)
    other = max(n - 1 - (1 if rem else 0), 1)
    widths = [name_w] + [(w - name_w - rem_w) / other] * other + ([rem_w] if rem else [])
    t = Table(body, colWidths=widths, repeatRows=1)
    sz = 9 if w == W else 7.5
    st = _grid_style(pal, len(body), 1, foot, sz, S.regular, S.bold, S) + [("ALIGN", (0, 0), (0, -1), "LEFT"), ("LEFTPADDING", (0, 0), (0, -1), 7),
                                                                         ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    t.setStyle(TableStyle(st))
    return [Spacer(1, 5), banner("Academic Performance", S, w), Spacer(1, 3), t]


def cumulative_table(cum, S, w=None):
    """Cumulative / Annual Performance: fixed column widths computed from the term count (same formula as
    _cumulative_breakdown.html), so the table is ALWAYS exactly the page width and Remark is never cut off."""
    w = w or W
    pal = S.pal
    ca3 = bool(cum.get("show_ca3"))
    terms = list(cum["terms"])
    per = 7 if ca3 else 6
    nt = len(terms)
    term_cols = nt * per
    overall_pct = 25.6
    col_pct = max(2.4, min(5.6, (100 - overall_pct - 10.5) / term_cols))
    subj_pct = 100 - overall_pct - term_cols * col_pct
    pt = w / 100.0
    widths = [subj_pct * pt] + [col_pct * pt] * term_cols + [4.8 * pt, 5.6 * pt, 3.8 * pt, 4.0 * pt, 7.4 * pt]
    fs = max(4.9, min(7.0, (col_pct * pt - 1.6) / 2.9))
    div = 4 if ca3 else 3
    sty_n = S.p(fs, align=TA_CENTER, leading=fs * 1.2)
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
    st = _grid_style(pal, n, 2, 2, fs, S.regular, S.bold, S)
    st += [("SPAN", (0, 0), (0, 1)), ("ALIGN", (0, 0), (0, -1), "LEFT"), ("LEFTPADDING", (0, 0), (0, -1), 4), ("FONTSIZE", (0, 0), (0, 1), 8.5),
           ("LEFTPADDING", (1, 0), (-1, -1), 1), ("RIGHTPADDING", (1, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (0, -1), 2),
           ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
           ("FONTSIZE", (1, 0), (-1, 0), 8.5), ("FONTSIZE", (1, 1), (-1, 1), max(4.6, fs - .7)),
           ("FONTSIZE", (0, n - 2), (-1, -1), max(4.6, fs - .7))]
    for i in range(nt):
        a = 1 + i * per
        st.append(("SPAN", (a, 0), (a + per - 1, 0)))
    o = 1 + term_cols
    st += [("SPAN", (o, 0), (o + 4, 0)), ("SPAN", (o + 1, n - 2), (o + 4, n - 2)), ("SPAN", (o + 1, n - 1), (o + 4, n - 1))]
    t.setStyle(TableStyle(st))
    return [Spacer(1, 5), banner("Cumulative / Annual Performance", S, w), Spacer(1, 3), t]


def summary_strip(cells, S, w=None, cols=None, with_banner=True):
    w = w or W
    pal, kind = S.pal, S.m["summ"]
    cols = cols or len(cells)
    head = [Spacer(1, 6), banner("Academic Performance Summary", S, w), Spacer(1, 3)] if with_banner else []
    if kind in ("topbar", "tiles"):
        gap = 5
        cw = (w - gap * (cols - 1)) / cols
        out, row_cells = [], []
        for i, (l, v) in enumerate(cells):
            tile = Table([[Paragraph(_esc(l), S.p(8.5, color=_mix(pal.accent, .7), bold=(kind == "topbar"), align=TA_CENTER))],
                          [Paragraph(_esc(v), S.p(14.5, bold=True, align=TA_CENTER, leading=17))]], colWidths=[cw])
            st = [("BACKGROUND", (0, 0), (-1, -1), colors.white if S.key == "dashboard_cards" else (pal.tint if kind == "topbar" else pal.band)),
                  ("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, 0), (-1, 0), 1), ("TOPPADDING", (0, 1), (-1, 1), 2), ("BOTTOMPADDING", (0, 1), (-1, 1), 7)]
            if kind == "topbar":
                st.append(("LINEABOVE", (0, 0), (-1, 0), 3.4, pal.second if i % 2 == 0 or S.key != "dashboard_cards" else pal.accent))
            if kind == "tiles" or S.key == "dashboard_cards":
                st += [("ROUNDEDCORNERS", [7] * 4)]
            if S.key == "dashboard_cards":
                st += [("BOX", (0, 0), (-1, -1), .5, pal.line)]
            tile.setStyle(TableStyle(st))
            row_cells.append(tile)
            if len(row_cells) == cols or i == len(cells) - 1:
                out += [_row_of(row_cells, [cw] * len(row_cells), gap=gap), Spacer(1, gap)]
                row_cells = []
        return head + out
    lab = [Paragraph(_esc(l) if kind != "plain" else _esc(l).upper(), S.p(9 if kind != "plain" else 7, bold=True, align=TA_CENTER)) for l, _v in cells]
    val = [Paragraph(_esc(v), S.p(14.5 if kind != "plain" else 18, bold=(kind != "plain"), align=TA_CENTER, leading=18 if kind != "plain" else 21)) for _l, v in cells]
    rows_l, rows_v = [], []
    for i in range(0, len(cells), cols):
        rows_l.append(lab[i:i + cols] + [""] * (cols - len(lab[i:i + cols])))
        rows_v.append(val[i:i + cols] + [""] * (cols - len(val[i:i + cols])))
    rows = []
    for a, b in zip(rows_l, rows_v):
        rows += [a, b]
    t = Table(rows, colWidths=[w / cols] * cols)
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    if kind == "plain":
        st += [("LINEBEFORE", (1, 0), (-1, -1), .6, pal.line), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    else:
        st += [("BOX", (0, 0), (-1, -1), 1.1, pal.line), ("ROUNDEDCORNERS", [5] * 4), ("BACKGROUND", (0, 0), (-1, -1), pal.tint), ("LINEBEFORE", (1, 0), (-1, -1), .6, pal.line),
               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
        for r in range(0, len(rows), 2):
            st.append(("LINEBELOW", (0, r), (-1, r), .6, pal.line))
            st += [("TOPPADDING", (0, r + 1), (-1, r + 1), 8), ("BOTTOMPADDING", (0, r + 1), (-1, r + 1), 8)]
    t.setStyle(TableStyle(st))
    return head + [t]


def domain_tables(groups, S, w=None, stack=False, with_banner=True):
    w = w or W
    pal = S.pal
    hw = w if stack else (w - GAP * 2) / 2
    solid = S.m["th"] == "solid"
    flat = S.m["th"] == "plain"
    small = stack
    tables = []
    for g in groups:
        hc = colors.white if solid else None
        rows = [[Paragraph(_esc(g["label"]), S.p(8.5 if small else 10.5, color=hc, bold=True)), Paragraph("Rating", S.p(8.5 if small else 10.5, color=hc, bold=True, align=TA_CENTER))]]
        for n, v in g["items"]:
            rows.append([Paragraph(_esc(n), S.p(7.6 if small else 9.5)), Paragraph(f"<b>{_esc(v)}</b>", S.p(7.6 if small else 9.5, align=TA_CENTER))])
        t = Table(rows, colWidths=[hw * .66, hw * .34])
        pad = 1.6 if small else 2.6
        st = [("BACKGROUND", (0, 0), (-1, -1), colors.white), ("LINEBELOW", (0, 0), (-1, -2), .5, pal.line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad), ("LEFTPADDING", (0, 0), (0, -1), 7)]
        if solid:
            st.append(("BACKGROUND", (0, 0), (-1, 0), pal.accent if S.key == "executive" else pal.solid))
        elif flat:
            st += [("LINEBELOW", (0, 0), (-1, 0), 1.1, pal.accent)]
        else:
            st.append(("BACKGROUND", (0, 0), (-1, 0), pal.tint))
        if not flat:
            st += [("BOX", (0, 0), (-1, -1), 1.1, pal.line), ("ROUNDEDCORNERS", [0] * 4 if S.m["box"] == "bar" else [5] * 4)]
        t.setStyle(TableStyle(st))
        tables.append(t)
    out = [Spacer(1, 3), banner("Domain Ratings", S, w), Spacer(1, 3)] if with_banner else []
    step = 1 if stack else 2
    for i in range(0, len(tables), step):
        pair = tables[i:i + step]
        out += [pair[0] if stack else _row_of(pair, [hw] * len(pair)), Spacer(1, GAP)]
    return out


def attendance(items, S, w=None, per_row=None):
    """items: [(label, value, weight)]"""
    w = w or W
    out = [Spacer(1, 2)]
    if per_row:
        for i in range(0, len(items), per_row):
            ch = items[i:i + per_row]
            tw = sum(x[2] for x in ch)
            avail = w - GAP * (len(ch) - 1)
            widths = [avail * x[2] / tw for x in ch]
            out += [_row_of([_label_box(l, v if v is not None else "—", wd, S, big=11) for (l, v, _w), wd in zip(ch, widths)], widths), Spacer(1, 4)]
        return out
    total_w = sum(x[2] for x in items)
    avail = w - GAP * (len(items) - 1)
    widths = [avail * x[2] / total_w for x in items]
    cells = [_label_box(l, v if v is not None else "—", wd, S, big=12) for (l, v, _w), wd in zip(items, widths)]
    return out + [_row_of(cells, widths), Spacer(1, GAP)]


def comments(items, S, w=None, stack=False):
    w = w or W
    n = 1 if stack else len(items)
    wd = (w - GAP * (n - 1)) / n
    cells = []
    for label, text in items:
        body = Paragraph((_esc(text).replace("\n", "<br/>")) or "&nbsp;", S.p(10.5 if not stack else 9.5, leading=13 if not stack else 11.5))
        cells.append(_box([[[Paragraph(_esc(label).upper(), S.p(7.5, color=S.pal.label)), body]]], [wd], S, pad=(3, 5, 6, 6), valign="TOP", row_heights=[1.9 * cm if not stack else 1.6 * cm]))
    if stack:
        out = []
        for c in cells:
            out += [c, Spacer(1, 5)]
        return out
    return [_row_of(cells, [wd] * len(cells)), Spacer(1, 6)]


def signatures(cells, S, w=None):
    """cells: [(role, sig_path, name, show_sig, show_date, date_iso)] -- ONE line above the name."""
    w = w or W
    pal = S.pal
    built = []
    colw = min(7.6 * cm, w / 2 - 8)
    for role, sig, name, show_sig, show_date, date_iso in cells:
        rows, st = [], []
        if show_sig:
            simg = _img(sig, 1.1 * cm, 4 * cm) if sig else None
            rows.append([simg if simg is not None else Spacer(1, 1.1 * cm)])
            st.append(("LINEBELOW", (0, 0), (0, 0), 1.1, pal.accent))
            rows.append([Paragraph(f"{_esc(role)}{(': ' + _esc(name)) if name else ''}", S.p(10 if w == W else 8.5, align=TA_CENTER))])
        if show_date:
            rows.append([Paragraph(f"Date: {format_dmy(date_iso) if date_iso else ''}", S.p(10 if w == W else 8.5, align=TA_CENTER))])
        t = Table(rows, colWidths=[colw])
        t.setStyle(TableStyle(st + [("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        built.append(t)
    hw = w / 2
    row = Table([[b for b in built] + [""] * (2 - len(built))], colWidths=[hw, hw])
    row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return [Spacer(1, 0.3 * cm), row]


def keys(grading, domain_key_on, S, w=None, narrow=False):
    w = w or W
    pal = S.pal
    left = right = None
    fs = 7.8 if not narrow else 6.6
    if grading:
        items = [Paragraph(f"{_esc(g['grade'])} = {g['min_score']:g} – {g['max_score']:g} ({_esc(g['remark'])})", S.p(7 if not narrow else 6.4, leading=9 if narrow else None)) for g in grading]
        if narrow:
            rows = [[i] for i in items]
            inner = Table(rows, colWidths=[w - 4])
        else:
            rows = [items[i:i + 3] + [""] * (3 - len(items[i:i + 3])) for i in range(0, len(items), 3)]
            inner = Table(rows, colWidths=[3.8 * cm] * 3)
        inner.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        left = [Paragraph("GRADING SCALE", S.p(8 if not narrow else 7, bold=True)), inner]
    if domain_key_on:
        txt = " &nbsp;".join(f"{k}&nbsp;=&nbsp;{v.replace(' ', '&nbsp;')}" for k, v in DOMAIN_LABELS.items())
        if narrow:
            txt = "<br/>".join(f"{k} = {v}" for k, v in DOMAIN_LABELS.items())
        right = [Paragraph("DOMAIN RATINGS SCALE", S.p(8 if not narrow else 7, bold=True)), Paragraph(txt, S.p(7 if not narrow else 6.4, leading=10 if not narrow else 8.5))]
    if not left and not right:
        return []
    if narrow:
        parts = (left or []) + [Spacer(1, 3)] + (right or [])
        return [Spacer(1, 3)] + parts
    if left and right:
        t = Table([[left, right]], colWidths=[11.4 * cm, w - 11.4 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBEFORE", (1, 0), (1, 0), .6, pal.line), ("LEFTPADDING", (1, 0), (1, 0), 10),
                               ("LEFTPADDING", (0, 0), (0, 0), 0), ("LINEABOVE", (0, 0), (-1, 0), 1.1, pal.line), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    else:
        t = Table([[left or right]], colWidths=[w])
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEABOVE", (0, 0), (-1, 0), 1.1, pal.line), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return [Spacer(1, 0.25 * cm), t]


# ---------------------------------------------------------------------------------------- full sheets
def _page_color(S):
    return {"white": colors.white, "gray": S.pal.gray}.get(S.m["page"], S.pal.page)


def result_elements(data, term, school_name, logo_path, student_full_name, styles, accent_color="#0b2a6f",
                    teacher_signature=None, principal_signature=None, regular="Helvetica", bold="Helvetica-Bold"):
    """The terminal result (per-term, or Cumulative/Annual when that state is on) as flowables, in the design the
    school chose in Result Display Settings. Returns (flowables, palette, watermark, page_colour)."""
    rs = data.get("rs") or {}
    info = data.get("info") or {}
    student, class_row = data["student"], data["class_row"]
    pal = Palette(rs, accent_color)
    S = Styles(pal, regular, bold, rs.get("template"))
    layout = S.m["layout"]
    cum = data.get("cumulative")
    show_cum = bool(cum and cum.get("terms"))
    name = student_full_name(student) if student_full_name else f"{student['last_name']} {student['first_name']}"

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

    if show_cum:
        cs = data.get("cum_summary") or {}
        mx = cs.get("max_each")
        pct = round(cs["average"] / mx * 100, 1) if cs.get("average") and mx else 0
        cells = [("Total Subjects", cs.get("subjects_written", "-")), ("Total Score", cs.get("total") if cs.get("total") is not None else "-"),
                 ("Average Score", cs.get("average", "-")), ("Percentage", f"{pct}%"), ("Grade", cs.get("grade", "-")), ("Remark", cs.get("remark", "-"))]
    else:
        tob = data.get("total_obtainable")
        pct = round(data["total"] / tob * 100, 1) if tob else 0
        cells = [("Total Subjects", data.get("subjects_written", "-")), ("Total Score", data["total"]), ("Average Score", data["average"]),
                 ("Percentage", f"{pct}%"), ("Grade", data.get("overall_grade", "-")), ("Remark", data.get("overall_remark", "-"))]
    cells = [(l, "-" if v is None else v) for l, v in cells]

    groups = data.get("domain_groups") if rs.get("show_domains", True) else None
    promo = data.get("promotion_status") if rs.get("show_promotion", True) else None
    att = []
    if rs.get("show_attendance", True):
        for flag, label, key in (("show_days_opened", "Days School Opened", "days_school_opened"), ("show_days_present", "Days Present", "days_present"),
                                 ("show_days_absent", "Days Absent", "days_absent"), ("show_days_late", "Days Late", "days_late")):
            if rs.get(flag, True):
                att.append((label, info.get(key), 1))
    if promo:
        att.append(("Promotion Status", promo, 2.4))
    cm_items = []
    if rs.get("show_teacher_comment", True):
        cm_items.append(("Class/Form Teacher's Comment", info.get("teacher_comment")))
    if rs.get("show_principal_comment", True):
        cm_items.append(("Principal's Comment", info.get("principal_comment")))
    sg = []
    if rs.get("show_teacher_signature", True) or rs.get("show_teacher_sign_date", True):
        sg.append(("Class Teacher", (teacher_signature or {}).get("path"), data.get("teacher_name"), rs.get("show_teacher_signature", True),
                   rs.get("show_teacher_sign_date", True), info.get("teacher_signed_date")))
    if rs.get("show_principal_signature", True) or rs.get("show_principal_sign_date", True):
        sg.append(("Principal", (principal_signature or {}).get("path"), data.get("principal_name"), rs.get("show_principal_signature", True),
                   rs.get("show_principal_sign_date", True), info.get("principal_signed_date")))
    ntr = [Spacer(1, 4), Paragraph(f"Next Term Resumes: <b>{_esc(rs['next_term_resumes'])}</b>", S.p(9))] if rs.get("next_term_resumes") else []
    scale = (rs.get("grading_scale") or []) if rs.get("show_grading_key", True) else []
    foot = [Spacer(1, 4), Paragraph(_esc(rs["footer"]), S.p(8))] if rs.get("footer") else []

    def table_part(w):
        return cumulative_table(cum, S, w) if show_cum else term_table(data, rs, S, w)

    els = header(data, term, rs, S, school_name, logo_path)

    if layout == "sidebar":
        SW, GP = 6.3 * cm, 0.45 * cm
        MW = W - SW - GP
        inner = SW - 16
        if show_cum:
            els += table_part(W)
        left = id_boxes(ids, S, inner)
        if att:
            left += attendance(att, S, inner, per_row=2)
        if groups:
            left += domain_tables(groups, S, inner, stack=True)
        left += ntr + keys(scale, bool(groups), S, inner, narrow=True)
        right = [] if show_cum else table_part(MW)
        right += summary_strip(cells, S, MW, cols=3)
        if cm_items:
            right += [Spacer(1, 6)] + comments(cm_items, S, MW, stack=True)
        if sg:
            right += signatures(sg, S, MW)
        lt = _rounded([[left]], [SW], pal, bg=pal.band, radius=8, line_w=0, pad=(8, 8, 8, 8), valign="TOP")
        two = Table([[lt, "", right]], colWidths=[SW, GP, MW])
        two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        els += [Spacer(1, 4), two] + foot
        return els, pal, rs.get("watermark"), _page_color(S)

    if layout == "cards":
        wi = W - 16
        els += [_card(id_boxes(ids, S, wi), W, S), Spacer(1, 6)]
        els += summary_strip(cells, S, W, with_banner=False)
        els += [_card(table_part(wi), W, S), Spacer(1, 6)]
        if groups:
            els += [_card(domain_tables(groups, S, wi), W, S), Spacer(1, 6)]
        half = (W - 8) / 2
        side = []
        if att:
            side.append(_card(attendance(att, S, half - 16, per_row=2), half, S))
        if cm_items:
            side.append(_card(comments(cm_items, S, half - 16, stack=True), half, S))
        if len(side) == 2:
            els += [_row_of(side, [half, half], gap=8), Spacer(1, 6)]
        elif side:
            els += [side[0], Spacer(1, 6)]
        if sg:
            els += [_card(signatures(sg, S, wi), W, S), Spacer(1, 6)]
        if scale or groups:
            els += [_card(keys(scale, bool(groups), S, wi), W, S)]
        els += ntr + foot
        return els, pal, rs.get("watermark"), _page_color(S)

    els += id_boxes(ids, S)
    els += table_part(W)
    els += summary_strip(cells, S)
    if groups:
        els += domain_tables(groups, S)
    if att:
        els += attendance(att, S)
    if cm_items:
        els += comments(cm_items, S)
    if sg:
        els += signatures(sg, S)
    els += ntr + keys(scale, bool(groups), S) + foot
    return els, pal, rs.get("watermark"), _page_color(S)


def cumulative_page_elements(data, session, school_name, logo_path, student_full_name, rs, accent_color="#0b2a6f", regular="Helvetica", bold="Helvetica-Bold"):
    """The dedicated Annual / Cumulative Result page (cumulative_result_print.html) as flowables."""
    rs = rs or {}
    pal = Palette(rs, accent_color)
    S = Styles(pal, regular, bold, rs.get("template"))
    student, class_row = data["student"], data["class_row"]
    name = student_full_name(student) if student_full_name else f"{student['last_name']} {student['first_name']}"
    sess_name = session["name"] if session is not None else ""
    els = header(None, None, rs, S, school_name, logo_path, title_override="Annual / Cumulative Result", session_line=sess_name)
    ids = [("Name", name, False), ("Admission / Register No.", student["admission_no"], False), ("Class / Arm", class_row["name"], False)]
    ids += [("Cumulative Average", data.get("average", "-"), False), ("Grade", f"{data.get('grade', '-')} ({data.get('remark', '')})", False)]
    pos = data.get("position")
    ids.append(("Overall Position", f"{pos}" + (f" of {data['class_size']}" if data.get("class_size") else ""), True))
    els += id_boxes(ids, S)
    cum = data.get("cumulative")
    if cum and cum.get("terms"):
        els += cumulative_table(cum, S)
    if rs.get("footer"):
        els += [Spacer(1, 4), Paragraph(_esc(rs["footer"]), S.p(8))]
    return els, pal, rs.get("watermark"), _page_color(S)
