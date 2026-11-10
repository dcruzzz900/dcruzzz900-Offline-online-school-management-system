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
  /* V104: staff/student sidebar menu (hamburger). One place, reliable on phones, tablets and desktops: opens/closes with the
     button, closes on Escape, on a tap outside (backdrop), on choosing a link, on rotating/resizing to a wide screen and when
     the page is restored from the back/forward cache; the page behind does not scroll while the menu is open. */
  function sidebar(){
    var btn=document.getElementById('sidebarToggle'),side=document.querySelector('.app-sidebar');
    if(!btn||!side)return;
    var small=window.matchMedia('(max-width:1000px)'),back=document.createElement('div');
    back.className='sidebar-backdrop';document.body.appendChild(back);
    function set(open){
      side.classList.toggle('open',open);back.classList.toggle('show',open&&small.matches);
      document.body.classList.toggle('nav-open',open&&small.matches);
      btn.setAttribute('aria-expanded',String(open));btn.setAttribute('aria-label',open?'Close menu':'Open menu');btn.textContent=open?'\u2715':'\u2630';
    }
    var closeBtn=document.createElement('button');closeBtn.type='button';closeBtn.className='sidebar-close';closeBtn.setAttribute('aria-label','Close menu');closeBtn.innerHTML='\u2715 <span>Close menu</span>';
    side.insertBefore(closeBtn,side.firstChild);closeBtn.addEventListener('click',function(){set(false);btn.focus();});
    btn.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();set(!side.classList.contains('open'));});
    back.addEventListener('click',function(){set(false);});
    document.addEventListener('keydown',function(e){if(e.key==='Escape')set(false);});
    side.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a');if(a&&small.matches)set(false);});
    var onChange=function(){if(!small.matches)set(false);};
    if(small.addEventListener)small.addEventListener('change',onChange);else if(small.addListener)small.addListener(onChange);
    window.addEventListener('resize',onChange);window.addEventListener('pageshow',function(){set(false);});
  }
  document.addEventListener('DOMContentLoaded',function(){greet();menu();sidebar();});
})();
