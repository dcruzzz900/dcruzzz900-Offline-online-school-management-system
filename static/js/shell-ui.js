(function(){
  /* Time-based greeting in the user's local time (night counts as evening). */
  function greet(){
    var h=new Date().getHours(),g=h<12?'Good morning':(h<17?'Good afternoon':'Good evening');
    document.querySelectorAll('[data-greeting]').forEach(function(el){el.textContent=g;});
  }
  /* Super Admin menu: collapse / expand on every screen size, remembered for the session. */
  function menu(){
    var top=document.querySelector('.platform-top'),btn=document.querySelector('.platform-nav-toggle'),nav=document.getElementById('platformNav');
    if(!top||!btn||!nav)return;
    var key='platformNavCollapsed',small=window.matchMedia('(max-width:820px)');
    function set(c){top.classList.toggle('nav-collapsed',c);btn.setAttribute('aria-expanded',String(!c));btn.textContent=c?'☰ Menu':'✕ Close menu';try{sessionStorage.setItem(key,c?'1':'0');}catch(e){}}
    var saved=null;try{saved=sessionStorage.getItem(key);}catch(e){}
    set(saved===null?small.matches:saved==='1');
    btn.addEventListener('click',function(e){e.preventDefault();set(!top.classList.contains('nav-collapsed'));});
    document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!top.classList.contains('nav-collapsed')&&small.matches)set(true);});
  }
  /* Header clock: shows Day, DD/MM/YYYY - h:mm AM/PM in the SCHOOL's timezone. It starts from the server's time (not the device clock)
     and only counts forward from there. */
  function clock(){
    var el=document.getElementById('topClock');if(!el||!el.dataset.now)return;
    var tz=el.dataset.tz||'Africa/Lagos',base=Date.parse(el.dataset.now),t0=Date.now();
    function fmt(ms){var d=new Date(ms),p=function(o){return new Intl.DateTimeFormat('en-GB',Object.assign({timeZone:tz},o)).format(d);};
      return p({weekday:'long'})+', '+p({day:'2-digit',month:'2-digit',year:'numeric'})+' \u2014 '+new Intl.DateTimeFormat('en-US',{timeZone:tz,hour:'numeric',minute:'2-digit',hour12:true}).format(d);}
    function tick(){el.textContent=fmt(base+(Date.now()-t0));}
    try{tick();setInterval(tick,15000);}catch(e){el.textContent=el.dataset.fallback||'';}
  }
  document.addEventListener('DOMContentLoaded',function(){greet();menu();clock();});
})();
