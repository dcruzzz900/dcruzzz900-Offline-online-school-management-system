import os,sys,tempfile,threading,logging,re,time
"""V112 browser scenarios (Playwright): v106 shell drawer, collapsible add panels, live roll-call tiles.
Run: python tests/v112b_scenarios.py   (needs the playwright chromium browser, like tests/v75_scenarios.py)"""
APP=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"]=tempfile.mkdtemp(); sys.path.insert(0,APP); sys.path.insert(0,APP+"/tests"); os.chdir(APP)
import app as A, wf_helper
from db import get_db
from werkzeug.security import generate_password_hash
logging.disable(logging.CRITICAL)
c=get_db(); c.execute("UPDATE users SET password_hash=?",(generate_password_hash("Pass1234"),)); c.commit(); c.close()
A.app.config["TESTING"]=False
threading.Thread(target=lambda:A.app.run(port=5097,use_reloader=False),daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
res=[]
def chk(n,ok): res.append((n,ok)); print(("PASS " if ok else "FAIL ")+n)
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1366,"height":800})
    ctx.route(re.compile(r"^https?://(?!127\.0\.0\.1)"),lambda r:r.abort())
    pg=ctx.new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    U="http://127.0.0.1:5097"
    pg.goto(U+"/login"); pg.fill("input[name=username]","admin"); pg.fill("input[name=password]","Pass1234"); pg.click("button[type=submit]"); pg.wait_for_load_state()
    pg.goto(U+"/my-class/1/roll-call")
    chk("roll call title has no script text", "<script" not in pg.title() and pg.title().startswith("Roll Call"))
    chk("tiles start at 3 present", pg.inner_text("#rcPresent")=="3" and pg.inner_text("#rcAbsent")=="0")
    pg.check("input[name^=status_][value=absent] >> nth=0"); pg.check("input[name^=status_][value=late] >> nth=1")
    chk("tiles follow the radios (1 present, 1 absent, 1 late)", (pg.inner_text("#rcPresent"),pg.inner_text("#rcAbsent"),pg.inner_text("#rcLate"))==("1","1","1"))
    for url,btn,panel in (("/admin/students","[data-open=addPanel]","addPanel"),("/admin/students","[data-open=bulkPanel]","bulkPanel"),("/admin/classes","[data-open=addPanel]","addPanel"),("/admin/terms","[data-open=termPanel]","termPanel"),("/admin/fees","[data-open=paymentPanel]","paymentPanel"),("/scores/1/1","[data-open=bulkPanel]","bulkPanel")):
        pg.goto(U+url); closed=not pg.evaluate(f"document.getElementById('{panel}').open")
        pg.click(btn); pg.wait_for_timeout(200)
        chk(f"{url}: {panel} is closed then opens from its button", closed and pg.evaluate(f"document.getElementById('{panel}').open"))
    pg.goto(U+"/dashboard"); pg.click("#sidebarToggle"); pg.wait_for_timeout(300)
    chk("hamburger opens drawer and Esc closes it", pg.evaluate("getComputedStyle(document.querySelector('.app-sidebar')).transform")=="none")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    chk("Esc closes the drawer", pg.evaluate("getComputedStyle(document.querySelector('.app-sidebar')).transform")!="none")
    chk("no JavaScript page errors", not errs)
    if errs: print(errs[:3])
    b.close()
bad=sum(1 for _,o in res if not o)
print(sum(1 for _,o in res if o),"passed",bad,"failed"); os._exit(1 if bad else 0)
