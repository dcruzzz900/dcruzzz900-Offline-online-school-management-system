"""Compare computed styles of v106 mock elements vs the live app at 1366x800 and print every property that differs.
Usage: python tools/v106_style_compare.py <path-to-unzipped-Modern-Screens-v106-folder>
(needs playwright + chromium; the mock folder holds index.html, css/modern.css and the numbered screens)"""
import os,sys,tempfile,threading,logging,re,time,json
APP=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); MOCK=os.path.abspath(sys.argv[1]); os.environ["DATA_DIR"]=tempfile.mkdtemp(); sys.path.insert(0,APP); sys.path.insert(0,APP+"/tests"); os.chdir(APP)
import app as A, wf_helper
from db import get_db
from werkzeug.security import generate_password_hash
logging.disable(logging.CRITICAL)
c=get_db(); c.execute("UPDATE users SET password_hash=?",(generate_password_hash("Pass1234"),)); c.commit(); c.close()
A.app.config["TESTING"]=False
threading.Thread(target=lambda:A.app.run(port=5092,use_reloader=False),daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
PROPS=["width","height","backgroundColor","color","fontSize","fontWeight","fontFamily","borderRadius","borderTopWidth","borderTopColor","paddingTop","paddingRight","paddingBottom","paddingLeft","boxShadow","marginBottom"]
JS="""(sel)=>{const e=document.querySelector(sel);if(!e)return null;const s=getComputedStyle(e);const o={};%s.forEach(p=>o[p]=s[p]);const r=e.getBoundingClientRect();o.w=Math.round(r.width);o.h=Math.round(r.height);return o}"""%json.dumps(PROPS)
# (label, mock page, mock selector, live url, live selector)
PAIRS=[
 ("topbar","08-students.html",".topbar","/admin/students",".topbar"),
 ("sidebar","08-students.html",".sidebar","/admin/students",".app-sidebar"),
 ("sidebar nav item","08-students.html",".sidebar .nav-item","/admin/students",".app-sidebar nav a"),
 ("sidebar active item","08-students.html",".sidebar .nav-item.active","/admin/students",".app-sidebar nav a.active"),
 ("page title","08-students.html",".page-header h2","/admin/students",".page-heading h1"),
 ("page subtitle","08-students.html",".page-header p","/admin/students",".page-heading p"),
 ("card","08-students.html",".card","/admin/students",".app-main .card"),
 ("kpi tile","08-students.html",".kpi-mini,.kpi","/admin/students",".stat-box"),
 ("table header cell","08-students.html","thead th","/admin/students","table.table thead th"),
 ("table body cell","08-students.html","tbody td","/admin/students","table.table tbody td"),
 ("primary button","08-students.html",".btn-primary,.btn.primary","/admin/students",".page-actions .btn-primary"),
 ("secondary button","08-students.html",".btn-secondary,.btn.secondary,.btn-outline","/admin/students",".page-actions .btn-secondary"),
 ("input","08-students.html","input[type=text],input.form-control,.search input","/admin/students","input.form-control, .form-select"),
 ("status badge","16-teacher-dashboard.html",".badge","/admin/terms",".badge"),
]
out=[]
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1366,"height":800})
    ctx.route(re.compile(r"^https?://(?!127\.0\.0\.1)"),lambda r:r.abort())
    live=ctx.new_page(); live.goto("http://127.0.0.1:5092/login"); live.fill("input[name=username]","admin"); live.fill("input[name=password]","Pass1234"); live.click("button[type=submit]"); live.wait_for_load_state()
    mock=ctx.new_page()
    for label,mp,msel,lu,lsel in PAIRS:
        mock.goto("file://"+MOCK+"/"+mp); 
        if lu!=getattr(live,'_last',None): live.goto("http://127.0.0.1:5092"+lu); live._last=lu; live.wait_for_timeout(300)
        # open drawers so sidebar measures
        m=mock.evaluate(JS,msel); l=live.evaluate(JS,lsel)
        out.append((label,m,l))
    b.close()
bad=0
for label,m,l in out:
    if m is None or l is None: print(f"?? {label}: mock={'ok' if m else 'MISSING'} live={'ok' if l else 'MISSING'}"); continue
    diffs=[]
    for k in PROPS+["w","h"]:
        if k in("fontFamily",): 
            if m[k].split(',')[0].strip('" ')!=l[k].split(',')[0].strip('" '): diffs.append((k,m[k].split(',')[0],l[k].split(',')[0]))
            continue
        if k in("width","height"): continue
        if k in("w","h"):
            if abs(m[k]-l[k])>max(6,0.05*m[k]) and label not in("card","sidebar","table header cell","table body cell","topbar" if k=="w" else ""): diffs.append((k,m[k],l[k]))
            continue
        if m[k]!=l[k]: diffs.append((k,m[k],l[k]))
    print(("OK   " if not diffs else "DIFF ")+label)
    for d in diffs: print("       %-16s mock=%-34s live=%s"%(d[0],str(d[1])[:34],str(d[2])[:40]))
    bad+=bool(diffs)
print("\n%d of %d components differ"%(bad,len(out)))
os._exit(0)
