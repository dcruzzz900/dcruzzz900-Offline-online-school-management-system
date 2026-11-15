#!/usr/bin/env python3
"""V106: derive static/css/theme-dark.generated.css from the app's own stylesheets.

The app's CSS was written in layers (v46 ... v105) with many literal colours. Rather than hand-patch hundreds of rules, this tool
walks every rule, and for each literal light background / dark text / light border emits a dark-mode counterpart scoped to
html[data-bs-theme="dark"] (screen only, so printing is never dark). Neutral and pastel surfaces are re-lit, dark text is lightened,
saturated brand colours and white-on-colour text are left alone. The result-sheet paper is never touched.
Run:  python3 tools/build_dark_css.py     (re-run after editing the source stylesheets)"""
import colorsys, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = ["style.css", "responsive-ui.css", "ai-ui.css", "ux-complete.css", "shell-modern.css", "admin-dashboard.css", "gender-panel.css"]
OUT = os.path.join(ROOT, "static/css/theme-dark.generated.css")
SKIP_SEL = re.compile(r"\.rs-|\.rsx|result-sheet|\.sheet-paper|\.print-|\.no-dark|::selection|\.gp\b|\.gp[-\s.>:{,]|\bsvg\.ico")
NAMED = {"white": (255, 255, 255), "black": (0, 0, 0)}
COLOR_RE = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)|\bwhite\b|\bblack\b")

def parse_color(tok):
    t = tok.lower()
    if t in NAMED: return (*NAMED[t], 1.0)
    if t.startswith("#"):
        h = t[1:]
        if len(h) == 3: h = "".join(c * 2 for c in h)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
    m = re.match(r"rgba?\(([^)]*)\)", t)
    if m:
        parts = [x.strip() for x in re.split(r"[,/\s]+", m.group(1).strip()) if x.strip()]
        try:
            vals = [float(p.rstrip("%")) for p in parts[:3]]
            a = float(parts[3].rstrip("%")) / (100 if parts[3].endswith("%") else 1) if len(parts) > 3 else 1.0
            return (*vals, a)
        except ValueError: return None
    return None

def fmt(r, g, b, a):
    r, g, b = (max(0, min(255, round(v))) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}" if a >= 0.999 else f"rgba({r},{g},{b},{round(a, 3)})"

def hls(c): return colorsys.rgb_to_hls(c[0] / 255, c[1] / 255, c[2] / 255)
def from_hls(h, l, s, a):
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))
    return fmt(r * 255, g * 255, b * 255, a)

def dark_bg(c):
    h, l, s = hls(c)
    if l < 0.62: return None                       # already dark / saturated brand: keep
    if s > 0.45 and l < 0.8: return None           # vivid mid colours (badges, buttons): keep
    if s < 0.12: h, s = 218 / 360, 0.3                 # neutrals take the app's blue-grey so they match the surface tokens
    return from_hls(h, 0.12 + (1 - l) * 0.55, min(s, 0.3) * (1 if s == 0.3 else 0.6), c[3])

def dark_text(c, bg_light_kept):
    h, l, s = hls(c)
    if bg_light_kept or l > 0.78: return None      # white-on-colour or sits on a light surface that stays light
    if l <= 0.5:
        if s < 0.12: h, s = 218 / 360, 0.25
        return from_hls(h, max(0.74, 0.97 - l * 0.6) if s > 0.15 else 0.97 - l * 0.55, min(s, 0.6), c[3])
    return from_hls(h, 0.72, min(s, 0.5), c[3])    # mid greys / muted

def dark_border(c):
    h, l, s = hls(c)
    if l < 0.6: return None
    return from_hls(h, 0.27 + (1 - l) * 0.5, min(s, 0.25) * 0.5, c[3])

def recolor(value, fn):
    changed = [False]
    def sub(m):
        c = parse_color(m.group(0))
        if not c: return m.group(0)
        out = fn(c)
        if out is None: return m.group(0)
        changed[0] = True; return out
    return COLOR_RE.sub(sub, value), changed[0]

def split_decls(body):
    return [d.strip() for d in re.split(r";(?![^()]*\))", body) if d.strip()]

def rules(css, ctx=""):
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0: break
        head = css[i:j].strip(); depth, k = 1, j + 1
        while k < n and depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0); k += 1
        body = css[j + 1:k - 1]
        if head.startswith("@"):
            if re.match(r"@(media|supports)", head): yield from rules(body, ctx + head + "||")
        else: yield ctx, head, body
        i = k

def main():
    emitted = {}
    for name in SRC:
        css = re.sub(r"/\*.*?\*/", "", open(os.path.join(ROOT, "static/css", name)).read(), flags=re.S)
        for ctx, sel, body in rules(css):
            if "print" in ctx or SKIP_SEL.search(sel): continue
            decls = [(d.split(":", 1)[0].strip().lower(), d.split(":", 1)[1].strip()) for d in split_decls(body) if ":" in d]
            props = dict(decls)
            bg_kept = False
            for p, v in decls:
                if p in ("background", "background-color") and "var(" not in v and "gradient" not in v:
                    cs = [parse_color(x) for x in COLOR_RE.findall(v)]
                    if cs and cs[0] and cs[0][3] > 0.5 and hls(cs[0])[1] >= 0.62 and dark_bg(cs[0]) is None: bg_kept = True
            out = []
            for p, v in decls:
                if "var(" in v and not COLOR_RE.search(v): continue
                imp = " !important" if "!important" in v else ""
                v2 = v.replace("!important", "").strip()
                if p in ("background", "background-color", "background-image"):
                    nv, ch = recolor(v2, dark_bg)
                elif p == "color":
                    nv, ch = recolor(v2, lambda c: dark_text(c, bg_kept))
                elif p.startswith("border") or p in ("outline", "outline-color"):
                    nv, ch = recolor(v2, dark_border)
                else: continue
                if ch: out.append(f"{p}:{nv}{imp}")
            if not out: continue
            sels = [x.strip() for x in re.split(r",(?![^()\[\]]*[)\]])", sel) if x.strip()]
            pref = ",".join('html[data-bs-theme="dark"] ' + x for x in sels)
            emitted.setdefault(ctx, []).append(pref + "{" + ";".join(out) + "}")
    parts = ["/* GENERATED by tools/build_dark_css.py - do not edit by hand. Dark-mode counterparts of the app stylesheets (screen only). */"]
    base = emitted.pop("", [])
    parts.append("@media screen{" + "".join(base) + "}")
    for ctx, lst in emitted.items():
        conds = [c for c in ctx.split("||") if c]
        inner = "".join(lst)
        for c in reversed(conds): inner = c + "{" + inner + "}"
        parts.append("@media screen{" + inner + "}")
    open(OUT, "w").write("\n".join(parts) + "\n")
    print(f"wrote {OUT}: {os.path.getsize(OUT)//1024} KB, {sum(len(v) for v in emitted.values()) + len(base)} rules")

if __name__ == "__main__": main()
