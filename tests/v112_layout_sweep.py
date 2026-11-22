import os,sys,tempfile,threading,logging,datetime as D,random
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.environ["DATA_DIR"]=tempfile.mkdtemp(prefix="ls_"); sys.path.insert(0,ROOT); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
logging.disable(logging.CRITICAL)
c=get_db(); c.execute("UPDATE users SET password_hash=?",(generate_password_hash("Pass1234"),))
term=c.execute("SELECT id FROM terms ORDER BY id DESC LIMIT 1").fetchone()[0]; studs=[r[0] for r in c.execute("SELECT id FROM students")]; subs=[r[0] for r in c.execute("SELECT subject_id FROM class_subjects")]
cls=c.execute("SELECT id FROM classes LIMIT 1").fetchone()[0]; sch=c.execute("SELECT id FROM schools LIMIT 1").fetchone()[0]; uid=c.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
for sid,(a,b,e) in {studs[0]:(18,17,55),studs[1]:(10,12,40),studs[2]:(2,3,10)}.items():
    for sub in subs: c.execute("INSERT INTO scores (student_id,subject_id,term_id,ca1,ca2,exam) VALUES (?,?,?,?,?,?)",(sid,sub,term,a,b,e))
random.seed(2); t=D.date.today()
for back in range(0,400):
    d=t-D.timedelta(days=back)
    if d.weekday()>4: continue
    for sid in studs: c.execute("INSERT INTO attendance_records (student_id,class_id,term_id,date,status) VALUES (?,?,?,?,?)",(sid,cls,term,d.isoformat(),'present' if random.random()<.88 else 'absent'))
    c.execute("INSERT INTO staff_attendance (school_id,user_id,date,status) VALUES (?,?,?,?)",(sch,uid,d.isoformat(),'Present'))
c.commit(); c.close()
from werkzeug.serving import make_server
srv=make_server('127.0.0.1',5084,A.app,threaded=True); threading.Thread(target=srv.serve_forever,daemon=True).start()
from playwright.sync_api import sync_playwright
PAGES={'admin':['/dashboard','/admin/students','/result/1','/broadsheet/1','/reports/analytics','/timetable','/admin/theme','/admin/classes'],'aokafor':['/dashboard','/teaching-workspace','/scores/1/1','/result/1']}
WIDTHS=[1280,1024,820,568,390,320]; SCALES=[90,100,150]
JS="""(()=>{const w=innerWidth;const doc=document.documentElement;const sw=doc.scrollWidth;
const clipped=[...document.querySelectorAll('main *, .topbar *')].filter(e=>{const r=e.getBoundingClientRect();if(r.width<1||r.height<1)return false;const cs=getComputedStyle(e);if(cs.position==='fixed')return false;if(r.right<=w+2&&r.left>=-2)return false;let a=e.parentElement;while(a&&a!==document.body){const o=getComputedStyle(a).overflowX;if(o==='auto'||o==='scroll'||o==='hidden')return false;a=a.parentElement}return true}).length;
const hid=[...document.querySelectorAll('main *, .topbar *, .portal-tabs *')].filter(e=>{const cs=getComputedStyle(e);if(cs.overflowX!=='hidden'&&cs.overflow!=='hidden')return false;if(e.scrollWidth<=e.clientWidth+2||e.clientWidth<4)return false;if(cs.textOverflow==='ellipsis')return false;return true}).map(e=>(e.className&&e.className.baseVal!==undefined?e.className.baseVal:e.className)||e.tagName).slice(0,4);
const f=document.getElementById('shFabBtn').getBoundingClientRect();
return {sw,w,clipped,hid,fab:f.left>=0&&f.right<=w&&f.top>=0&&f.bottom<=innerHeight}})()"""
with sync_playwright() as p:
    b=p.chromium.launch(); bad=[]; n=0
    for user,pages in PAGES.items():
        ctx=b.new_context(viewport={'width':1280,'height':900}); pg=ctx.new_page()
        pg.goto('http://127.0.0.1:5084/login'); pg.fill('input[name=username]',user); pg.fill('input[name=password]','Pass1234'); pg.click('form button[type=submit]'); pg.wait_for_timeout(1800)
        for u in pages:
            for w in WIDTHS:
                pg.set_viewport_size({'width':w,'height':900})
                pg.goto('http://127.0.0.1:5084'+u); 
                for sc in SCALES:
                    pg.evaluate(f"document.documentElement.setAttribute('data-font-scale','{sc}')"); pg.wait_for_timeout(90)
                    r=pg.evaluate(JS); n+=1
                    if r['sw']>w+1 or r['clipped'] or r['hid'] or not r['fab']: bad.append((user,u,w,sc,r))
    print('checked',n,'combinations; problems:',len(bad))
    for x in bad[:25]: print(' ',x)
    b.close()
