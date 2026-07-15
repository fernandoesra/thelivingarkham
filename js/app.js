/* ============================================================
   The Living Arkham — app logic
   Loads the grimoire data (data/grimoire_*.json) + icon manifest at runtime.
   ============================================================ */
(function () {
"use strict";

var UI = {
  es:{onthispage:"En esta página",entries:"entradas",start:"Inicio",searchph:"Buscar reglas, palabras clave, iconos…",
      nores:"Sin resultados",insec:"en",sub:"Grimorio interactivo · Arkham Horror LCG",jump:"Saltar a",fig:"Figura del Grimorio · pág.",
      loaderr:"No se pudo cargar el grimorio."},
  en:{onthispage:"On this page",entries:"entries",start:"Home",searchph:"Search rules, keywords, icons…",
      nores:"No results",insec:"in",sub:"Interactive rulebook · Arkham Horror LCG",jump:"Jump to",fig:"Grimoire figure · p.",
      loaderr:"Could not load the grimoire."}
};

var GRIM = {}, ICONS = {};
var root=document.getElementById('tla-root');
var elNav=document.getElementById('tla-nav'), elMain=document.getElementById('tla-main'),
    elToc=document.getElementById('tla-toc'), elQ=document.getElementById('tla-q'),
    elRes=document.getElementById('tla-results');
var lang='es', data=null, curSec=null, searchIndex={}, resSel=-1;

/* ---------- helpers ---------- */
function esc(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function iconHTML(name){return '<i class="ico ico-'+name+'" title="'+((ICONS[name]&&ICONS[name][lang])||name)+'"></i>';}
function runsHTML(runs){
  var h='';
  for(var i=0;i<runs.length;i++){var r=runs[i];
    if(r.kind==='icon'){h+=iconHTML(r.name);}
    else if(r.kind==='link'){h+='<a class="xref" data-t="'+esc(r.target)+'">'+wrap(esc(r.t),r)+'</a>';}
    else{h+=wrap(esc(r.t),r);}
  }
  return h;
}
function wrap(t,r){if(r.bold)t='<strong>'+t+'</strong>'; if(r.italic)t='<em>'+t+'</em>'; return t;}
function blocksHTML(blocks){
  var h='',i=0;
  while(i<blocks.length){
    var b=blocks[i];
    if(b.type==='bullet'){
      h+='<ul class="tla-bul">';
      while(i<blocks.length && blocks[i].type==='bullet'){
        h+='<li class="'+(blocks[i].level===2?'l2':'l1')+'">'+runsHTML(blocks[i].runs)+'</li>'; i++;
      }
      h+='</ul>';
    } else { h+='<p class="tla-p">'+runsHTML(b.runs)+'</p>'; i++; }
  }
  return h;
}
function plainOfRuns(runs){var s='';for(var i=0;i<runs.length;i++){s+=runs[i].kind==='text'||runs[i].kind==='link'?runs[i].t:(' '+((ICONS[runs[i].name]&&ICONS[runs[i].name][lang])||'')+' ');}return s;}
function plainOfBlocks(blocks){return blocks.map(function(b){return plainOfRuns(b.runs);}).join(' ');}
function titleHTML(e){return e.titleRuns?runsHTML(e.titleRuns):esc(e.title);}

/* ---------- build search index ---------- */
function buildIndex(){
  ['es','en'].forEach(function(L){
    var arr=[]; GRIM[L].sections.forEach(function(s){
      if(s.intro&&s.intro.length){arr.push({sid:s.id,eid:s.id,title:s.title,sec:s.title,num:s.num,text:plainOfBlocks(s.intro),isSec:true});}
      (s.entries||[]).forEach(function(e){arr.push({sid:s.id,eid:e.id,title:e.title,titleRuns:e.titleRuns,sec:s.title,num:s.num,text:plainOfBlocks(e.blocks)});});
    });
    searchIndex[L]=arr;
  });
}

/* ---------- NAV ---------- */
function sectionEntries(s){return s.entries||[];}
function buildNav(){
  var h=''; data.sections.forEach(function(s,si){
    var n=sectionEntries(s).length;
    var num=s.num?('<span class="tla-nav-num">'+s.num+'</span>'):'<span class="tla-nav-num">•</span>';
    var cnt=n?('<span class="tla-nav-cnt">'+n+'</span>'):'';
    h+='<div class="tla-nav-sec" data-si="'+si+'" id="navsec-'+s.id+'">';
    h+='<button class="tla-nav-btn" type="button" data-si="'+si+'">'+num+'<span>'+esc(s.title)+'</span>'+cnt+'</button>';
    if(s.kind==='glossary'){
      h+='<div class="tla-sublist"><div class="tla-az">'+azBar(s)+'</div></div>';
    } else if(n){
      h+='<div class="tla-sublist">';
      sectionEntries(s).forEach(function(e){h+='<button class="tla-sublink" type="button" data-eid="'+esc(e.id)+'">'+titleHTML(e)+'</button>';});
      h+='</div>';
    }
    h+='</div>';
  });
  elNav.innerHTML=h;
}
function azBar(s){
  var letters={}; sectionEntries(s).forEach(function(e){var c=e.title.replace(/[“"'¿¡(]/g,'').charAt(0).toUpperCase();if(/[A-ZÑ0-9]/.test(c))letters[c]=e.id;});
  var order='ABCDEFGHIJKLMNÑOPQRSTUVWXYZ0123456789'.split('');
  return order.filter(function(c){return letters[c];}).map(function(c){return '<button type="button" data-eid="'+esc(letters[c])+'">'+c+'</button>';}).join('');
}

/* ---------- render section ---------- */
function render(sid,eid,flash){
  var s=data.sections.filter(function(x){return x.id===sid;})[0]; if(!s)s=data.sections[0];
  curSec=s;
  var h='';
  h+='<div class="tla-crumb">'+(s.num?('· '+s.num+' ·'):'')+' The Living Arkham</div>';
  h+='<h1 class="tla-h1">'+(s.num?'<span class="tla-rn">'+s.num+'.</span>':'')+esc(s.title)+'</h1>';
  h+='<div class="tla-rule"></div>';
  if(s.kind==='intro'){h+=introHTML(s);}
  if(s.intro&&s.intro.length){h+='<div class="tla-lead">'+blocksHTML(s.intro)+'</div>';}
  if(s.figures&&s.figures.length){
    h+='<div class="tla-figs">';
    s.figures.forEach(function(f){
      h+='<figure class="tla-fig"><img loading="lazy" src="assets/img/'+esc(f.file)+'" alt=""><figcaption>'+UI[lang].fig+' '+f.page+'</figcaption></figure>';});
    h+='</div>';
  }
  sectionEntries(s).forEach(function(e){
    h+='<article class="tla-entry'+(e.sub?' sub':'')+'" id="e-'+esc(e.id)+'">';
    h+='<h3>'+titleHTML(e)+'<a class="anchor" href="#'+lang+'/'+esc(e.id)+'" title="'+UI[lang].jump+'" aria-label="'+UI[lang].jump+'">§</a></h3>';
    h+=blocksHTML(e.blocks);
    h+='</article>';
  });
  elMain.innerHTML=h;
  buildToc(s);
  markNav(sid);
  if(eid){var t=document.getElementById('e-'+eid); if(t){t.scrollIntoView({block:'start'}); if(flash){t.classList.remove('flash');void t.offsetWidth;t.classList.add('flash');}}}
  else{elMain.scrollTop=0; window.scrollTo({top:offsetTop(root),behavior:'auto'});}
}
function introHTML(s){
  return lang==='es'
    ?'<div class="tla-note"><b>Bienvenido/a.</b> Esta es una versión interactiva de <b>El Grimorio de Arkham</b>: la recopilación completa de aclaraciones de reglas de <i>Arkham Horror: El Juego de Cartas</i>. Usa el buscador (tecla <b>/</b>), navega por el glosario alfabético y sigue los enlaces cruzados. Cambia entre <b>ES (v1.0)</b> e <b>EN (v1.1)</b> arriba a la derecha.</div>'
    :'<div class="tla-note"><b>Welcome.</b> This is an interactive edition of <b>The Arkham Grimoire</b>: the complete rules-clarification compendium for <i>Arkham Horror: The Card Game</i>. Use search (press <b>/</b>), browse the alphabetical glossary and follow the cross-links. Switch between <b>ES (v1.0)</b> and <b>EN (v1.1)</b> at the top right.</div>';
}

/* ---------- TOC (right) ---------- */
function buildToc(s){
  var items=[];
  sectionEntries(s).forEach(function(e){items.push({id:e.id,label:titleHTML(e),sub:e.sub});});
  if(!items.length){elToc.innerHTML=''; return;}
  var h='<h4>'+UI[lang].onthispage+'</h4>';
  items.forEach(function(it){h+='<a href="#'+lang+'/'+esc(it.id)+'" data-eid="'+esc(it.id)+'" style="'+(it.sub?'padding-left:18px;':'')+'">'+it.label+'</a>';});
  elToc.innerHTML=h;
}
function markNav(sid){
  [].forEach.call(elNav.querySelectorAll('.tla-nav-btn'),function(b){b.classList.remove('active');});
  [].forEach.call(elNav.querySelectorAll('.tla-nav-sec'),function(d){d.classList.remove('open');});
  var sec=document.getElementById('navsec-'+sid);
  if(sec){sec.classList.add('open'); var b=sec.querySelector('.tla-nav-btn'); if(b){b.classList.add('active'); b.scrollIntoView({block:'nearest'});}}
}
function offsetTop(el){var y=0;while(el){y+=el.offsetTop;el=el.offsetParent;}return y-8;}

/* ---------- scroll spy ---------- */
var spyRAF=null;
function spy(){
  if(spyRAF)return; spyRAF=requestAnimationFrame(function(){spyRAF=null;
    var arts=elMain.querySelectorAll('.tla-entry'); var top=120,cur=null;
    for(var i=0;i<arts.length;i++){var r=arts[i].getBoundingClientRect(); if(r.top<=top+40)cur=arts[i].id.slice(2); else break;}
    [].forEach.call(elToc.querySelectorAll('a'),function(a){a.classList.toggle('on',a.getAttribute('data-eid')===cur);});
    [].forEach.call(elNav.querySelectorAll('.tla-sublink'),function(a){a.classList.toggle('active',a.getAttribute('data-eid')===cur);});
  });
}

/* ---------- routing (URL hash = single source of truth) ---------- */
var lastFlash=false;
function findEntry(L,eid){
  var g=GRIM[L]; for(var i=0;i<g.sections.length;i++){var s=g.sections[i]; if(s.id===eid)return{sid:s.id,eid:null};
    for(var j=0;j<(s.entries||[]).length;j++){if(s.entries[j].id===eid)return{sid:s.id,eid:eid};}}
  return null;
}
function applyLang(L){
  lang=L; data=GRIM[L]; root.setAttribute('data-lang',L); document.documentElement.setAttribute('lang',L);
  [].forEach.call(document.querySelectorAll('.tla-lang button'),function(b){b.setAttribute('aria-pressed',b.getAttribute('data-l')===L);});
  document.getElementById('tla-sub').textContent=UI[L].sub;
  elQ.setAttribute('placeholder',UI[L].searchph);
  buildNav();
}
function setHash(L,target,flash){
  lastFlash=flash!==false;
  var h='#'+L+'/'+target;
  if(location.hash===h){route();} else {location.hash=h;}
  closeNav();
}
function navigate(target,flash){setHash(lang,target,flash);}
function gotoTarget(eid,flash){var f=findEntry(lang,eid); if(f)setHash(lang,f.eid||f.sid,flash);}
function route(){
  var m=(location.hash||'').replace(/^#/,'').split('/');
  var L=(m[0]==='en'||m[0]==='es')?m[0]:lang;
  if(L!==lang)applyLang(L);
  var target=m[1], f=target?findEntry(L,target):null;
  if(f){render(f.sid,f.eid,lastFlash);} else {render(data.sections[0].id,null,false);}
  lastFlash=false; closeResults();
}
/* ---------- language ---------- */
function setLang(L){
  if(L===lang)return;
  var idx=curSec?data.sections.indexOf(curSec):0;
  var sid=(GRIM[L].sections[idx]||GRIM[L].sections[0]).id;
  setHash(L,sid,false);
}

/* ---------- SEARCH ---------- */
function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');}
function search(q){
  q=norm(q.trim()); if(q.length<2){closeResults();return;}
  var terms=q.split(/\s+/), arr=searchIndex[lang], out=[];
  for(var i=0;i<arr.length;i++){var it=arr[i]; var hayT=norm(it.title), hayX=norm(it.text);
    var score=0,ok=true;
    for(var t=0;t<terms.length;t++){var tm=terms[t];
      var inT=hayT.indexOf(tm), inX=hayX.indexOf(tm);
      if(inT<0&&inX<0){ok=false;break;}
      if(inT===0)score+=100; else if(inT>0)score+=40; if(inX>=0)score+=6;
    }
    if(ok){out.push({it:it,score:score});}
  }
  out.sort(function(a,b){return b.score-a.score||a.it.title.length-b.it.title.length;});
  renderResults(out.slice(0,40),terms);
}
function hl(text,terms){
  var t=esc(text);
  terms.forEach(function(tm){if(!tm)return; var re=new RegExp('('+tm.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig');
    t=t.replace(re,'<mark>$1</mark>');});
  return t;
}
function snippet(text,terms){
  var nt=norm(text),pos=-1; for(var i=0;i<terms.length;i++){var p=nt.indexOf(terms[i]); if(p>=0&&(pos<0||p<pos))pos=p;}
  if(pos<0)pos=0; var st=Math.max(0,pos-40); var frag=text.slice(st,st+160); if(st>0)frag='…'+frag; return frag;
}
function renderResults(list,terms){
  if(!list.length){elRes.innerHTML='<div class="tla-res-empty">'+UI[lang].nores+'</div>'; elRes.classList.add('on'); resSel=-1; setExpanded(true); return;}
  var h=''; list.forEach(function(o,i){var it=o.it;
    h+='<div class="tla-res" role="option" data-eid="'+esc(it.eid)+'" data-i="'+i+'">';
    h+='<div class="rt">'+(it.titleRuns?runsHTML(it.titleRuns):hl(it.title,terms))+'<span class="rs">'+(it.num?it.num+' · ':'')+esc(it.sec)+'</span></div>';
    h+='<div class="rx">'+hl(snippet(it.text,terms),terms)+'</div></div>';
  });
  elRes.innerHTML=h; elRes.classList.add('on'); resSel=-1; setExpanded(true);
}
function closeResults(){elRes.classList.remove('on'); elRes.innerHTML=''; setExpanded(false);}
function setExpanded(v){elQ.setAttribute('aria-expanded',v?'true':'false');}
function moveSel(d){var items=elRes.querySelectorAll('.tla-res'); if(!items.length)return;
  resSel=(resSel+d+items.length)%items.length;
  [].forEach.call(items,function(x,i){x.classList.toggle('sel',i===resSel); if(i===resSel)x.scrollIntoView({block:'nearest'});});
}

/* ---------- mobile nav ---------- */
function openNav(){elNav.classList.add('on');document.getElementById('tla-scrim').classList.add('on');document.getElementById('tla-burger').setAttribute('aria-expanded','true');}
function closeNav(){elNav.classList.remove('on');document.getElementById('tla-scrim').classList.remove('on');document.getElementById('tla-burger').setAttribute('aria-expanded','false');}

/* ---------- events ---------- */
function wireEvents(){
  elNav.addEventListener('click',function(e){
    var b=e.target.closest('.tla-nav-btn'); if(b){var si=+b.getAttribute('data-si'); navigate(data.sections[si].id,false); return;}
    var sl=e.target.closest('[data-eid]'); if(sl){gotoTarget(sl.getAttribute('data-eid'),true);}
  });
  elMain.addEventListener('click',function(e){
    var x=e.target.closest('.xref'); if(x){e.preventDefault(); gotoTarget(x.getAttribute('data-t'),true); return;}
    var a=e.target.closest('.anchor'); if(a){e.preventDefault(); gotoTarget(a.getAttribute('href').split('/')[1],true); return;}
    var img=e.target.closest('.tla-fig img'); if(img){lightbox(img.src);}
  });
  elToc.addEventListener('click',function(e){var a=e.target.closest('[data-eid]'); if(a){e.preventDefault(); gotoTarget(a.getAttribute('data-eid'),true);}});
  elRes.addEventListener('click',function(e){var r=e.target.closest('.tla-res'); if(r){var eid=r.getAttribute('data-eid'); elQ.value=''; closeResults(); gotoTarget(eid,true); elQ.blur();}});
  document.querySelector('.tla-lang').addEventListener('click',function(e){var b=e.target.closest('button'); if(b)setLang(b.getAttribute('data-l'));});
  document.getElementById('tla-home').addEventListener('click',function(e){e.preventDefault(); navigate(data.sections[0].id,false);});
  document.getElementById('tla-burger').addEventListener('click',function(){elNav.classList.contains('on')?closeNav():openNav();});
  document.getElementById('tla-scrim').addEventListener('click',closeNav);

  var qTimer=null;
  elQ.addEventListener('input',function(){clearTimeout(qTimer); qTimer=setTimeout(function(){search(elQ.value);},110);});
  elQ.addEventListener('focus',function(){if(elQ.value.trim().length>=2)search(elQ.value);});
  elQ.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){e.preventDefault();moveSel(1);}
    else if(e.key==='ArrowUp'){e.preventDefault();moveSel(-1);}
    else if(e.key==='Enter'){var items=elRes.querySelectorAll('.tla-res'); var pick=items[resSel<0?0:resSel]; if(pick){elQ.value='';closeResults();gotoTarget(pick.getAttribute('data-eid'),true);elQ.blur();}}
    else if(e.key==='Escape'){elQ.value='';closeResults();elQ.blur();}
  });
  document.addEventListener('click',function(e){if(!e.target.closest('.tla-search'))closeResults();});
  document.addEventListener('keydown',function(e){
    if(e.key==='/'&&document.activeElement!==elQ&&!/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)){e.preventDefault();elQ.focus();elQ.select();}
  });
  window.addEventListener('scroll',spy,{passive:true});
  elMain.addEventListener('scroll',spy,{passive:true});
  window.addEventListener('hashchange',route);

  var lb=document.getElementById('tla-lb');
  lb.addEventListener('click',function(){this.classList.remove('on');});
}
function lightbox(src){var lb=document.getElementById('tla-lb'); lb.querySelector('img').src=src; lb.classList.add('on');}

/* ---------- boot: fetch data, then init ---------- */
function boot(){
  Promise.all([
    fetch('data/grimoire_es.json').then(function(r){return r.json();}),
    fetch('data/grimoire_en.json').then(function(r){return r.json();}),
    fetch('assets/icons/icons.json').then(function(r){return r.json();})
  ]).then(function(res){
    GRIM.es=res[0]; GRIM.en=res[1]; ICONS=res[2];
    data=GRIM[lang];
    buildIndex();
    buildNav();
    wireEvents();
    route();
  }).catch(function(err){
    elMain.innerHTML='<div class="tla-note"><b>'+UI[lang].loaderr+'</b><br>'+esc(String(err))+'</div>';
    console.error('The Living Arkham:',err);
  });
}
boot();
})();
