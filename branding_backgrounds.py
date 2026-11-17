"""V107: Theme & Branding backgrounds - presets, custom colour, gradients - in ONE pure module (no Flask / DB imports).

The CSS is always BUILT HERE from validated values (a preset key, '#rrggbb' colours, an angle); user text is never put into CSS.
Every background has a light and a dark rendering, and the text colour that sits directly on it is chosen by real WCAG contrast
(white or near-black, whichever is more readable), so text stays readable on every selection."""
import re

HEX = re.compile(r"#[0-9a-fA-F]{6}")
MODES = ("default", "preset", "solid", "gradient")
DARK_BASE = "#0B1120"

# key: (label, light_a, light_b, dark_a, dark_b, angle)
PRESETS = {
    "sky":      ("Soft Sky",      "#eaf4ff", "#f7fbff", "#0f1c33", "#0B1120", 160),
    "mint":     ("Fresh Mint",    "#e6f7ef", "#f6fffb", "#0e2a24", "#0B1120", 160),
    "sand":     ("Warm Sand",     "#fbf1de", "#fffaf0", "#2a2216", "#0B1120", 160),
    "lavender": ("Lavender Mist", "#efe9ff", "#faf8ff", "#1e1a35", "#0B1120", 160),
    "slate":    ("Calm Slate",    "#e9edf4", "#f8fafc", "#151d2e", "#0B1120", 160),
    "ocean":    ("Ocean",         "#0ea5e9", "#2563eb", "#0c4a6e", "#1e3a8a", 135),
    "sunset":   ("Sunset",        "#f97316", "#db2777", "#7c2d12", "#831843", 135),
    "emerald":  ("Emerald",       "#10b981", "#047857", "#064e3b", "#022c22", 135),
}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_ink(*backgrounds):
    """white or near-black - whichever has the better WORST-CASE contrast against every colour the text may sit on"""
    best, score = "#ffffff", -1
    for ink in ("#ffffff", "#111827"):
        worst = min(contrast(ink, b) for b in backgrounds)
        if worst > score:
            best, score = ink, worst
    return best


def _mix(c, base, pct_base):
    r1, g1, b1 = _rgb(c)
    r2, g2, b2 = _rgb(base)
    k = pct_base / 100
    return "#%02x%02x%02x" % (round(r1 * (1 - k) + r2 * k), round(g1 * (1 - k) + g2 * k), round(b1 * (1 - k) + b2 * k))


def clean(mode, preset, c1, c2, angle):
    """validate raw form values -> safe values (anything invalid falls back; nothing user-supplied survives unchecked)"""
    mode = mode if mode in MODES else "default"
    preset = preset if preset in PRESETS else "sky"
    c1 = c1 if isinstance(c1, str) and HEX.fullmatch(c1) else "#e6f0ff"
    c2 = c2 if isinstance(c2, str) and HEX.fullmatch(c2) else "#ffffff"
    try:
        angle = max(0, min(360, int(angle)))
    except (TypeError, ValueError):
        angle = 160
    return mode, preset, c1.lower(), c2.lower(), angle


def _scrim(ink, colours, target=4.6):
    """smallest translucent overlay (black under white text / white under dark text) that lifts the WORST contrast to `target`"""
    base = "#000000" if ink == "#ffffff" else "#ffffff"
    for step in range(0, 46):
        a = step * 0.02
        if min(contrast(ink, _mix(c, base, a * 100)) for c in colours) >= target:
            return round(a, 2)
    return 0.9


def build(mode, preset="sky", c1="#e6f0ff", c2="#ffffff", angle=160):
    """-> None for the standard look, or {'light','dark','ink_light','ink_dark'}: CSS background values (with a computed scrim when the
    colours alone cannot give text 4.5:1 contrast) and the readable text colour for each theme."""
    mode, preset, c1, c2, angle = clean(mode, preset, c1, c2, angle)
    if mode == "default":
        return None
    if mode == "preset":
        _l, la, lb, da, db, ang = PRESETS[preset]
    elif mode == "solid":
        la = lb = c1
        da = db = _mix(c1, DARK_BASE, 78)
        ang = 180
    else:   # gradient
        la, lb, ang = c1, c2, angle
        da, db = _mix(c1, DARK_BASE, 78), _mix(c2, DARK_BASE, 78)

    def one(a, b):
        grad = a if a == b else f"linear-gradient({ang}deg,{a},{b})"
        ink = readable_ink(a, b)
        alpha = _scrim(ink, (a, b))
        if alpha:
            s = "0,0,0" if ink == "#ffffff" else "255,255,255"
            grad = f"linear-gradient(rgba({s},{alpha}),rgba({s},{alpha})),{grad}"
        return grad, ink

    (cl, il), (cd, idk) = one(la, lb), one(da, db)
    return {"light": cl, "dark": cd, "ink_light": il, "ink_dark": idk}


def worst_contrast(mode, preset="sky", c1="#e6f0ff", c2="#ffffff", angle=160):
    """test helper: the lowest text/background contrast in light and dark AFTER the scrim (what a reader actually gets)"""
    mode, preset, c1, c2, angle = clean(mode, preset, c1, c2, angle)
    if mode == "default":
        return 21.0
    if mode == "preset":
        _l, la, lb, da, db, _a = PRESETS[preset]
    elif mode == "solid":
        la = lb = c1; da = db = _mix(c1, DARK_BASE, 78)
    else:
        la, lb, da, db = c1, c2, _mix(c1, DARK_BASE, 78), _mix(c2, DARK_BASE, 78)
    r = build(mode, preset, c1, c2, angle)
    out = []
    for cols, ink, css in (((la, lb), r["ink_light"], r["light"]), ((da, db), r["ink_dark"], r["dark"])):
        m = re_alpha(css)
        base = "#000000" if ink == "#ffffff" else "#ffffff"
        out.append(min(contrast(ink, _mix(c, base, m * 100)) for c in cols))
    return min(out)


def re_alpha(css):
    m = re.match(r"linear-gradient\(rgba\(\d+,\d+,\d+,([0-9.]+)\)", css)
    return float(m.group(1)) if m else 0.0
