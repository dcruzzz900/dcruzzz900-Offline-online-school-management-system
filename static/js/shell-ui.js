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
  document.addEventListener('DOMContentLoaded',function(){greet();menu();});
})();
