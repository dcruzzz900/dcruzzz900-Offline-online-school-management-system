#!/usr/bin/env python3
"""V106: work Bootstrap 5 classes into the Jinja templates (idempotent - safe to re-run).

  <input>/<textarea>  -> form-control (checkbox/radio -> form-check-input, range -> form-range, color -> form-control-color)
  <select>            -> form-select
  <table>             -> table table-hover align-middle, wrapped in .table-responsive
  .btn                -> btn btn-primary (when it has no variant), btn-small -> btn-sm
Skipped on purpose: the result sheet / cumulative sheet / print and PDF templates (paper must not change), the sign-in screens
(they have their own designed layout), templates that do not extend base.html, and any tag whose class attribute sits inside a
Jinja {% if %} (rewriting it could change a branch)."""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "templates")
SKIP_NAME = re.compile(r"^(_result_sheet|_cumulative|_print|.*_print\.html$|.*pdf.*|email_.*|base\.html$)")
AUTH_MARK = re.compile(r"school-auth-page|hub-auth-screen|\bauth-page\b|auth-card")
stats = {"input": 0, "select": 0, "textarea": 0, "table": 0, "btn": 0, "skipped_tags": 0}

def tag_end(s, i):
    """index just past the '>' that closes the tag starting at s[i] == '<', skipping Jinja blocks and quoted strings"""
    n, q = len(s), None
    j = i
    while j < n:
        if s.startswith("{{", j):
            j = s.find("}}", j) + 2; continue
        if s.startswith("{%", j):
            j = s.find("%}", j) + 2; continue
        if s.startswith("{#", j):
            j = s.find("#}", j) + 2; continue
        c = s[j]
        if q:
            if c == q: q = None
        elif c in "\"'": q = c
        elif c == ">": return j + 1
        j += 1
    return -1

def add_classes(tag, name, classes, drop=()):
    has_jinja_cond = "{%" in tag
    m = re.search(r'\bclass="([^"]*)"', tag)
    if m:
        if has_jinja_cond and re.search(r"\{%[^%]*%\}[^<>]*\bclass=", tag): return tag, False
        cur = m.group(1).split()
        new = [c for c in cur if c not in drop]
        for c in classes.split():
            if c not in new: new.append(c)
        if new == cur: return tag, False
        return tag[:m.start()] + 'class="' + " ".join(new) + '"' + tag[m.end():], True
    if re.search(r"\bclass=", tag): return tag, False          # class=... in a form we do not parse (single quotes / jinja)
    m2 = re.search(r"(\s*/?>)$", tag)
    return tag[:m2.start()] + ' class="' + classes + '"' + tag[m2.start():], True

def input_classes(tag):
    t = re.search(r'\btype="?([a-zA-Z]+)', tag)
    typ = (t.group(1).lower() if t else "text")
    if typ in ("hidden", "submit", "button", "image", "reset"): return None
    if typ in ("checkbox", "radio"): return "form-check-input"
    if typ == "range": return "form-range"
    if typ == "color": return "form-control form-control-color"
    return "form-control"

def convert(src):
    out, i, n = [], 0, len(src)
    pat = re.compile(r"<(input|select|textarea|table)\b", re.I)
    while True:
        m = pat.search(src, i)
        if not m: out.append(src[i:]); break
        out.append(src[i:m.start()])
        j = tag_end(src, m.start())
        if j < 0: out.append(src[m.start():]); break
        tag, name = src[m.start():j], m.group(1).lower()
        if re.search(r'id="topSearchInput"|data-no-bs|\bno-bs\b', tag): out.append(tag); i = j; continue
        if name == "input": cls = input_classes(tag)
        elif name == "select": cls = "form-select"
        elif name == "textarea": cls = "form-control"
        else: cls = "table table-hover align-middle"
        if cls:
            if name == "table" and re.search(r'\b(rs-|no-bs|rsx-|broad-print)', tag): cls = None
        if cls:
            tag2, changed = add_classes(tag, name, cls)
            if changed: stats[name] += 1
            elif "{%" in tag and re.search(r"\bclass=", tag): stats["skipped_tags"] += 1
            tag = tag2
        out.append(tag); i = j
    return "".join(out)

def wrap_tables(src):
    def repl(m):
        block = m.group(0)
        if block.count("<table") != 1: return block
        return '<div class="table-responsive">' + block + "</div>"
    # only tables that are not already inside a scroll wrapper on the same line / preceding tag
    res, pos = [], 0
    for m in re.finditer(r"<table\b.*?</table>", src, re.S):
        before = src[max(0, m.start() - 160):m.start()]
        if re.search(r'(table-responsive|table-wrap|scroll-x|overflow-x|tbl-wrap|table-scroll|x-scroll)[^<]*>\s*$', before): continue
        res.append((m.start(), m.end()))
    for a, b in reversed(res):
        blk = src[a:b]
        if blk.count("<table") != 1: continue
        src = src[:a] + '<div class="table-responsive">' + blk + "</div>" + src[b:]
    return src

def convert_buttons(src):
    def repl(m):
        cls = m.group(2).split()
        if "btn" not in cls: return m.group(0)
        cls = ["btn-sm" if c == "btn-small" else c for c in cls]
        variants = [c for c in cls if re.match(r"btn-(primary|secondary|success|danger|warning|info|light|dark|link|gold|accent|outline-.*)$", c)]
        if not variants: cls.insert(cls.index("btn") + 1, "btn-primary")
        stats["btn"] += 1
        return m.group(1) + " ".join(dict.fromkeys(cls)) + m.group(3)
    return re.sub(r'(<(?:a|button|input|label)\b[^>]*?\bclass=")([^"{}]*\bbtn\b[^"{}]*)(")', repl, src)

def main(dry=False):
    changed = 0
    for fn in sorted(os.listdir(TPL)):
        p = os.path.join(TPL, fn)
        if not fn.endswith(".html") or SKIP_NAME.match(fn): continue
        s = open(p, encoding="utf-8").read()
        if "{% extends" not in s[:400] and not fn.startswith("_") and "partials" not in fn: continue
        if AUTH_MARK.search(s): continue
        t = wrap_tables(convert(s)); t = convert_buttons(t)
        if t != s:
            changed += 1
            if not dry: open(p, "w", encoding="utf-8").write(t)
    print("templates changed:", changed, stats)

if __name__ == "__main__": main(dry="--dry" in sys.argv)
