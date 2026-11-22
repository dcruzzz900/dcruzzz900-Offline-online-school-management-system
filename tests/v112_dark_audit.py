import os,sys,tempfile,threading,logging,json,datetime as D,random
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.environ["DATA_DIR"]=tempfile.mkdtemp(prefix="da_"); sys.path.insert(0,ROOT); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
logging.disable(logging.CRITICAL)
pw=generate_password_hash("Pass1234"); c=get_db(); c.execute("UPDATE users SET password_hash=?",(pw,)); c.execute("INSERT INTO platform_admins(name,username,password_hash) VALUES('Root','root',?)",(pw,))
term=c.execute("SELECT id FROM terms ORDER BY id DESC LIMIT 1").fetchone()[0]; studs=[r[0] for r in c.execute("SELECT id FROM students")]; subs=[r[0] for r in c.execute("SELECT subject_id FROM class_subjects")]
for sid,(a,b,e) in {studs[0]:(18,17,55),studs[1]:(10,12,40),studs[2]:(2,3,10)}.items():
    for sub in subs: c.execute("INSERT INTO scores (student_id,subject_id,term_id,ca1,ca2,exam) VALUES (?,?,?,?,?,?)",(sid,sub,term,a,b,e))
c.commit(); c.close()
from werkzeug.serving import make_server
srv=make_server('127.0.0.1',5082,A.app,threaded=True); threading.Thread(target=srv.serve_forever,daemon=True).start()
from playwright.sync_api import sync_playwright
allr=sorted(r.rule for r in A.app.url_map.iter_rules() if "GET" in r.methods and "<" not in r.rule and not r.rule.startswith(("/static","/parent","/student")) and not any(k in r.rule for k in ("logout","download","pdf","export","print","csv","template","backup")))
extra={'admin':['/result/1','/broadsheet/1','/scores/1/1','/class/1/results'],'teacher':['/result/1','/broadsheet/1','/scores/1/1']}
JS="""(()=>{
function parse(c){const m=c.match(/rgba?\\(([^)]+)\\)/);if(!m)return null;const p=m[1].split(',').map(x=>parseFloat(x));return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}}
function lum(c){const f=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)};return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b)}
function blend(top,bot){const a=top.a;return {r:top.r*a+bot.r*(1-a),g:top.g*a+bot.g*(1-a),b:top.b*a+bot.b*(1-a),a:1}}
function bgOf(el){let layers=[];let n=el;while(n&&n.nodeType===1){const cs=getComputedStyle(n);if(cs.backgroundImage&&cs.backgroundImage!=='none'&&/gradient|url/.test(cs.backgroundImage))return null;const c=parse(cs.backgroundColor);if(c&&c.a>0){layers.push(c);if(c.a>=1)break}n=n.parentElement}
 let base={r:18,g:24,b:42,a:1};for(let i=layers.length-1;i>=0;i--)base=blend(layers[i],base);return base}
const bad=[];const seen=new Set();
const all=document.querySelectorAll('main *, .topbar *, .sidebar *, .portal-tabs *, .mobile-tabs *, #shFab *');
for(const el of all){
  if(!el.childNodes||![...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim().length>0))continue;
  const r=el.getBoundingClientRect();if(r.width<2||r.height<2)continue;const cs=getComputedStyle(el);if(cs.visibility==='hidden'||cs.display==='none'||parseFloat(cs.opacity)<0.2)continue;
  if(el.closest('.rs-screen-wrap,.sty-card,.rs-sheet,[class*="result-sheet"],.ad-banner,.ad-kpi,[class^="k-"]'))continue;
  let fg=parse(el.tagName.toLowerCase()==='tspan'||el instanceof SVGElement?cs.fill:cs.color);if(!fg)continue;const bg=bgOf(el);if(!bg)continue;if(fg.a<1)fg=blend(fg,bg);
  const L1=lum(fg),L2=lum(bg),ratio=(Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);
  const size=parseFloat(cs.fontSize),large=size>=24||(size>=18.66&&parseInt(cs.fontWeight)>=700);
  if(ratio<(large?3:4.5)){const key=(el.className&&el.className.baseVal!==undefined?el.className.baseVal:el.className)+'|'+cs.color+'|'+ratio.toFixed(1);if(seen.has(key))continue;seen.add(key);
    bad.push({tag:el.tagName.toLowerCase(),cls:String(el.className&&el.className.baseVal!==undefined?el.className.baseVal:el.className).slice(0,50),txt:el.textContent.trim().slice(0,30),ratio:+ratio.toFixed(2),fg:cs.color,size})}
}
return bad.slice(0,12)})()"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for who,login,user in (('admin','/login','admin'),('teacher','/login','aokafor'),('platform','/platform/login','root')):
        ctx=b.new_context(viewport={'width':1280,'height':900}); pg=ctx.new_page()
        pg.goto('http://127.0.0.1:5082'+login); pg.fill('input[name=username]',user); pg.fill('input[name=password]','Pass1234'); pg.click('form button[type=submit]'); pg.wait_for_timeout(1800)
        pg.evaluate("document.documentElement.setAttribute('data-bs-theme','dark')")
        routes=[u for u in allr if (u.startswith('/platform'))==(who=='platform')]+extra.get(who,[])
        res={};n=0
        for u in routes:
            try:
                r=pg.goto('http://127.0.0.1:5082'+u,timeout=8000)
                if not r or r.status!=200: continue
                pg.evaluate("document.documentElement.setAttribute('data-bs-theme','dark')"); pg.wait_for_timeout(120)
                bad=pg.evaluate(JS); n+=1
                if bad: res[u]=bad
            except Exception as e: pass
        print(f'== {who}: {n} pages audited, {len(res)} with low-contrast text')
        agg={}
        for u,bl in res.items():
            for x in bl: agg.setdefault((x['tag'],x['cls'],x['fg']),[]).append((u,x['ratio'],x['txt']))
        for k,v in sorted(agg.items(),key=lambda kv:-len(kv[1]))[:25]: print('  ',k,'x%d'%len(v),'e.g.',v[0])
    b.close()
