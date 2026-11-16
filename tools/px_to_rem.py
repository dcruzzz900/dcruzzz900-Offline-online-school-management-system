#!/usr/bin/env python3
"""V107: convert `font-size: Npx` to rem (N/16) in the app stylesheets and in templates' inline styles, so ONE root font-size
(desktop boost x the user's A-/A+ choice) scales every screen's text. Identical size at the 100% setting. Idempotent.
Never touched: result-sheet.css and the printable sheet / print / PDF / email templates (paper must not change)."""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS_SKIP = {"result-sheet.css", "theme-dark.generated.css"}
TPL_SKIP = re.compile(r"^(_result_sheet|_cumulative|_print|.*_print\.html$|.*pdf.*|email_.*)")
pat = re.compile(r"(font-size\s*:\s*)(\d+(?:\.\d+)?)px")
def conv(m):
    rem = round(float(m.group(2)) / 16, 4)
    return f"{m.group(1)}{rem:g}rem"
n = 0
for d, skip in (("static/css", None), ("templates", TPL_SKIP), ("templates/partials", TPL_SKIP)):
    for fn in sorted(os.listdir(os.path.join(ROOT, d))):
        p = os.path.join(ROOT, d, fn)
        if not (fn.endswith(".css") or fn.endswith(".html")) or fn in CSS_SKIP or (skip and skip.match(fn)): continue
        s = open(p, encoding="utf-8").read()
        t, c = pat.subn(conv, s)
        if c: open(p, "w", encoding="utf-8").write(t); n += c
print("font-size px -> rem conversions:", n)
