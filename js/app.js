/* ============================================================
   The Living Arkham — app logic
   Loads the grimoire data (data/grimoire_*.json) + icon manifest at runtime.
   ============================================================ */
(function () {
"use strict";

var UI = {
  es:{onthispage:"En esta página",entries:"entradas",searchph:"Buscar reglas, palabras clave, iconos…",
      nores:"Sin resultados",sub:"Grimorio interactivo · Arkham Horror LCG",jump:"Saltar a",fig:"Figura del Grimorio · pág.",
      loaderr:"No se pudo cargar el grimorio.",filterby:"Filtrar por letra",all:"Todas",
      tolight:"Cambiar a tema claro",todark:"Cambiar a tema oscuro",showing:"mostrando",of:"de",
      news:"Novedades",newver:"Nueva versión",newentries:"Entradas nuevas",updentries:"Entradas actualizadas",
      newbadge:"Nuevo",updbadge:"Ampliado",seenews:"Ver novedades",origpage:"orig. pág.",
      addedin:"añadido en v",updatedin:"ampliado en v",current:"versión actual",released:"publicada el",
      searchbtn:"Buscar…",cancel:"Cancelar",searchtitle:"Buscar en el grimorio",
      khnav:"navegar",khopen:"abrir",khclose:"cerrar",browse:"Explorar el grimorio",about:"Acerca de este grimorio original de FFG",
      rmkicker:"Rincón Miskatonic",rmtitle:"Un proyecto de Rincón Miskatonic",rmcta:"Visitar Rincón Miskatonic",
      rmbody:"<b>The Living Arkham</b> es la edición web —interactiva y disponible en varios idiomas— de <i>El Grimorio de Arkham</i>, la recopilación oficial de aclaraciones de reglas de FFG. Es una herramienta <b>gratuita</b> de <b>Rincón Miskatonic</b>, nuestro blog sobre <i>Arkham Horror: El Juego de Cartas</i>, donde encontrarás guías, ayudas y más <b>material gratuito</b> del juego.",
      faqlabel:"Ver documento (FAQ retiradas)",faqurl:"https://www.asmodee.es/product/arkham-horror-el-juego-de-cartas/",
      footsrc:"Basado en <b>El Grimorio de Arkham</b> v1.0 (ES) / v1.1 (EN) · reglas © sus autores · Arkham Horror: LCG ™ Fantasy Flight Games",
      footby:"The Living Arkham <b>v0.1.0 · beta</b> · un proyecto de <a href=\"https://rinconmiskatonic.org/\" target=\"_blank\" rel=\"noopener\">Rincón Miskatonic</a>",
      newsintro:"Esto es lo que cambió respecto a la versión anterior. En rojo se resalta el texto nuevo dentro de cada entrada."},
  en:{onthispage:"On this page",entries:"entries",searchph:"Search rules, keywords, icons…",
      nores:"No results",sub:"Interactive rulebook · Arkham Horror LCG",jump:"Jump to",fig:"Grimoire figure · p.",
      loaderr:"Could not load the grimoire.",filterby:"Filter by letter",all:"All",
      tolight:"Switch to light theme",todark:"Switch to dark theme",showing:"showing",of:"of",
      news:"What's New",newver:"New version",newentries:"New entries",updentries:"Updated entries",
      newbadge:"New",updbadge:"Expanded",seenews:"See what's new",origpage:"orig. p.",
      addedin:"added in v",updatedin:"expanded in v",current:"current version",released:"released",
      searchbtn:"Search…",cancel:"Cancel",searchtitle:"Search the grimoire",
      khnav:"navigate",khopen:"open",khclose:"close",browse:"Browse the grimoire",about:"About this original FFG grimoire",
      rmkicker:"Rincón Miskatonic",rmtitle:"A Rincón Miskatonic project",rmcta:"Visit Rincón Miskatonic",
      rmbody:"<b>The Living Arkham</b> is the web edition —interactive and available in several languages— of <i>The Arkham Grimoire</i>, FFG's official rules-clarification compendium. It's a <b>free</b> tool by <b>Rincón Miskatonic</b>, our blog about <i>Arkham Horror: The Card Game</i>, where you'll find guides, resources and more <b>free material</b> for the game.",
      faqlabel:"Open document (retired FAQ)",faqurl:"https://ffgapp.com/qr/legacy-faq",
      footsrc:"Based on <b>The Arkham Grimoire</b> v1.0 (ES) / v1.1 (EN) · rules © their authors · Arkham Horror: LCG ™ Fantasy Flight Games",
      footby:"The Living Arkham <b>v0.1.0 · beta</b> · a project by <a href=\"https://rinconmiskatonic.org/\" target=\"_blank\" rel=\"noopener\">Rincón Miskatonic</a>",
      newsintro:"Here is what changed since the previous version. New text within each entry is highlighted."}
};
var MONTHS={es:['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'],
            en:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']};
function fmtDate(iso){if(!iso)return''; var p=iso.split('-'); if(p.length<3)return iso;
  return (+p[2])+' '+MONTHS[lang][(+p[1])-1]+' '+p[0];}
function latestInfo(g){ // returns {v,date} of the newest version if it carries changes, else null
  if(!g.versions||g.versions.length<2)return null;
  var last=g.versions[g.versions.length-1];
  return (g.whatsnew&&g.whatsnew[last.v])?last:null;
}

var GRIM = {}, ICONS = {};
var BLOG='https://rinconmiskatonic.org/', SIGIL_SVG='';
var root=document.getElementById('tla-root');
var elNav=document.getElementById('tla-nav'), elMain=document.getElementById('tla-main'),
    elToc=document.getElementById('tla-toc'), elQ=document.getElementById('tla-q'),
    elRes=document.getElementById('tla-results'), elLive=document.getElementById('tla-live'),
    elTheme=document.getElementById('tla-theme'),
    elSModal=document.getElementById('tla-searchmodal'),
    elSOpen=document.getElementById('tla-search-open'),
    elSCancel=document.getElementById('tla-search-cancel');
var lang='es', data=null, curSec=null, searchIndex={}, resSel=-1, glossFilter='all', firstRoute=true;

/* ---------- helpers ---------- */
function esc(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function announce(msg){if(elLive){elLive.textContent=''; setTimeout(function(){elLive.textContent=msg;},40);}}
function iconHTML(name){return '<i class="ico ico-'+name+'" title="'+((ICONS[name]&&ICONS[name][lang])||name)+'"></i>';}
function runsHTML(runs,suppressNew){
  var h='';
  for(var i=0;i<runs.length;i++){var r=runs[i];
    if(r.kind==='icon'){h+=iconHTML(r.name); continue;}
    if(r.kind==='pageref'){h+='<span class="tla-pageref" title="'+UI[lang].origpage+' '+esc(r.n)+'">('+UI[lang].origpage+' '+esc(r.n)+')</span>'; continue;}
    var inner=(r.kind==='link')?'<a class="xref" data-t="'+esc(r.target)+'">'+wrap(esc(r.t),r)+'</a>':wrap(esc(r.t),r);
    if(r.v && !suppressNew){inner='<span class="tla-new" title="'+UI[lang].addedin+r.v+'">'+inner+'</span>';}
    h+=inner;
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
    } else { h+='<p class="tla-p">'+runsHTML(b.runs)+'</p>'+faqLink(plainOfRuns(b.runs)); i++; }
  }
  return h;
}
/* The PDF shows a QR to the retired-FAQ document after these sentences; render a real link instead. */
function faqLink(txt){
  var t=(txt||'').trim();
  if(!/(preguntas frecuentes retirad|retired FAQ)/i.test(t) || !/[:：]\s*$/.test(t)) return '';
  return '<a class="tla-extlink" href="'+UI[lang].faqurl+'" target="_blank" rel="noopener">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg>'
    +esc(UI[lang].faqlabel)+'</a>';
}
function plainOfRuns(runs){var s='';for(var i=0;i<runs.length;i++){s+=runs[i].kind==='text'||runs[i].kind==='link'?runs[i].t:(' '+((ICONS[runs[i].name]&&ICONS[runs[i].name][lang])||'')+' ');}return s;}
function plainOfBlocks(blocks){return blocks.map(function(b){return plainOfRuns(b.runs);}).join(' ');}
function titleHTML(e){return e.titleRuns?runsHTML(e.titleRuns,true):esc(e.title);}
function verBadge(e){
  if(e.newIn)return '<span class="tla-vbadge new" title="'+UI[lang].addedin+e.newIn+'">'+UI[lang].newbadge+' v'+e.newIn+'</span>';
  if(e.updatedIn)return '<span class="tla-vbadge upd" title="'+UI[lang].updatedin+e.updatedIn+'">'+UI[lang].updbadge+' v'+e.updatedIn+'</span>';
  return '';
}

/* ---------- theme ---------- */
function currentTheme(){return document.documentElement.getAttribute('data-theme')==='light'?'light':'dark';}
function applyThemeLabel(){var t=currentTheme(); if(elTheme)elTheme.setAttribute('aria-label', t==='dark'?UI[lang].tolight:UI[lang].todark);}
function setTheme(t){document.documentElement.setAttribute('data-theme',t); try{localStorage.setItem('tla-theme',t);}catch(e){} applyThemeLabel();}
function toggleTheme(){setTheme(currentTheme()==='dark'?'light':'dark');}

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

/* ---------- version history helpers ---------- */
function normalizeData(g){
  var li=latestInfo(g);
  if(li && !g.sections.some(function(x){return x.id==='novedades';})){
    g.sections.splice(1,0,{num:'',id:'novedades',kind:'whatsnew',title:UI[g.lang].news,ver:li,intro:[],entries:[],figures:[]});
  }
}
function wnCount(s){var wn=data.whatsnew&&data.whatsnew[s.ver.v]; return wn?(wn['new'].length+wn.updated.length):0;}

/* ---------- entries / filtering ---------- */
function sectionEntries(s){return s.entries||[];}
function entryLetter(e){var c=(e.title||'').replace(/[“"'¿¡().]/g,'').charAt(0).toUpperCase();return /[0-9]/.test(c)?'#':c;}
function visibleEntries(s){
  var all=sectionEntries(s);
  if(s.kind==='glossary' && glossFilter!=='all'){return all.filter(function(e){return entryLetter(e)===glossFilter;});}
  return all;
}

/* ---------- NAV ---------- */
function buildNav(){
  var h=''; data.sections.forEach(function(s,si){
    var news=s.kind==='whatsnew';
    var n=sectionEntries(s).length;
    var num=news?'<span class="tla-nav-num">✦</span>':(s.num?('<span class="tla-nav-num">'+s.num+'</span>'):'<span class="tla-nav-num">•</span>');
    var cnt=news?('<span class="tla-nav-cnt new">'+wnCount(s)+'</span>'):(n?('<span class="tla-nav-cnt">'+n+'</span>'):'');
    h+='<div class="tla-nav-sec'+(news?' is-news':'')+'" data-si="'+si+'" id="navsec-'+s.id+'">';
    h+='<button class="tla-nav-btn" type="button" data-si="'+si+'">'+num+'<span>'+esc(s.title)+'</span>'+cnt+'</button>';
    if(s.kind!=='glossary' && n){
      h+='<div class="tla-sublist">';
      sectionEntries(s).forEach(function(e){h+='<button class="tla-sublink" type="button" data-eid="'+esc(e.id)+'">'+titleHTML(e)+'</button>';});
      h+='</div>';
    }
    h+='</div>';
  });
  elNav.innerHTML=h;
}

/* ---------- A-Z filter bar (glossary) ---------- */
function azFilterBar(s){
  var present={}; sectionEntries(s).forEach(function(e){present[entryLetter(e)]=1;});
  var order='ABCDEFGHIJKLMNÑOPQRSTUVWXYZ'.split(''); if(present['#'])order.push('#');
  var total=sectionEntries(s).length, shown=visibleEntries(s).length;
  var h='<div class="tla-azfilter"><div class="tla-azlabel">'+UI[lang].filterby+'</div><div class="tla-azrow">';
  h+='<button class="tla-azbtn all'+(glossFilter==='all'?' active':'')+'" type="button" data-az="all" aria-pressed="'+(glossFilter==='all')+'">'+UI[lang].all+'</button>';
  order.forEach(function(c){ if(present[c]) h+='<button class="tla-azbtn'+(glossFilter===c?' active':'')+'" type="button" data-az="'+esc(c)+'" aria-pressed="'+(glossFilter===c)+'">'+c+'</button>'; });
  h+='<span class="tla-azcount">'+(glossFilter==='all'?total:shown+' '+UI[lang].of+' '+total)+' '+UI[lang].entries+'</span>';
  h+='</div></div>';
  return h;
}
function setGlossFilter(v){
  glossFilter=v; render(curSec.id,null,false); elMain.scrollTop=0;
  var n=visibleEntries(curSec).length;
  announce((v==='all'?UI[lang].all:v)+': '+n+' '+UI[lang].entries);
}

/* ---------- render section ---------- */
function render(sid,eid,flash){
  var s=data.sections.filter(function(x){return x.id===sid;})[0]; if(!s)s=data.sections[0];
  curSec=s;
  if(s.kind==='whatsnew'){renderWhatsNew(s); markNav(sid); return;}
  if(s.kind==='intro'){renderLanding(s); markNav(sid); return;}
  var ents=visibleEntries(s);
  var h='<div class="tla-doc">';
  h+='<div class="tla-crumb">'+(s.num?('· '+s.num+' ·'):'')+' The Living Arkham</div>';
  h+='<h1 class="tla-h1">'+(s.num?'<span class="tla-rn">'+s.num+'.</span>':'')+esc(s.title)+'</h1>';
  h+='<div class="tla-rule"></div>';
  if(s.intro&&s.intro.length){h+='<div class="tla-lead">'+blocksHTML(s.intro)+'</div>';}
  if(s.figures&&s.figures.length){
    h+='<div class="tla-figs">';
    s.figures.forEach(function(f){
      h+='<figure class="tla-fig"><img loading="lazy" src="assets/img/'+esc(f.file)+'" alt=""><figcaption>'+UI[lang].fig+' '+f.page+'</figcaption></figure>';});
    h+='</div>';
  }
  if(s.kind==='glossary'){h+=azFilterBar(s);}
  ents.forEach(function(e){
    var isNew=!!e.newIn;
    h+='<article class="tla-entry'+(e.sub?' sub':'')+(isNew?' is-new':'')+(e.updatedIn?' is-upd':'')+'" id="e-'+esc(e.id)+'">';
    h+='<h3>'+titleHTML(e)+verBadge(e)+'<a class="anchor" href="#'+lang+'/'+esc(e.id)+'" title="'+UI[lang].jump+'" aria-label="'+UI[lang].jump+'">§</a></h3>';
    h+=blocksHTML(e.blocks,isNew);
    h+='</article>';
  });
  h+='</div>';
  elMain.innerHTML=h;
  buildToc(s,ents);
  markNav(sid);
  if(eid){var t=document.getElementById('e-'+eid); if(t){t.scrollIntoView({block:'start'}); if(flash){t.classList.remove('flash');void t.offsetWidth;t.classList.add('flash');}}}
  else{elMain.scrollTop=0;}
}
function verBanner(li){
  return '<button class="tla-verbanner" type="button" data-go="novedades">'
    +'<span class="tla-vb-star">✦</span>'
    +'<span class="tla-vb-main"><span class="tla-vb-t">'+UI[lang].newver+' · v'+li.v+'</span>'
    +'<span class="tla-vb-d">'+UI[lang].released+' '+fmtDate(li.date)+'</span></span>'
    +'<span class="tla-vb-cta">'+UI[lang].seenews+' →</span></button>';
}
function renderWhatsNew(s){
  var li=s.ver, wn=data.whatsnew[li.v];
  var h='<div class="tla-doc">';
  h+='<div class="tla-crumb">The Living Arkham</div>';
  h+='<h1 class="tla-h1">'+esc(UI[lang].news)+'</h1><div class="tla-rule"></div>';
  h+='<div class="tla-note"><b>'+UI[lang].newver+' · v'+li.v+'</b> · '+UI[lang].released+' '+fmtDate(li.date)+'.<br>'+esc(UI[lang].newsintro)+'</div>';
  if(wn['new'].length){h+='<h3 class="tla-wnh"><span class="tla-vbadge new">'+UI[lang].newbadge+'</span> '+UI[lang].newentries+' <span class="tla-wncount">'+wn['new'].length+'</span></h3>'+wnList(wn['new'],'new');}
  if(wn.updated.length){h+='<h3 class="tla-wnh"><span class="tla-vbadge upd">'+UI[lang].updbadge+'</span> '+UI[lang].updentries+' <span class="tla-wncount">'+wn.updated.length+'</span></h3>'+wnList(wn.updated,'upd');}
  h+='</div>';
  elMain.innerHTML=h; elToc.innerHTML=''; elMain.scrollTop=0;
}
function wnList(items,cls){
  var h='<div class="tla-wngrid">';
  items.forEach(function(it){h+='<button class="tla-wncard '+cls+'" type="button" data-eid="'+esc(it.id)+'">'
    +'<span class="tla-wntitle">'+esc(it.title)+'</span>'
    +'<span class="tla-wnsec">'+(it.num?it.num+' · ':'')+esc(it.sec)+'</span></button>';});
  return h+'</div>';
}
function rmPanel(){
  return '<section class="tla-rm">'
    +'<div class="tla-rm-body">'
      +'<h2 class="tla-rm-title">'+esc(UI[lang].rmtitle)+'</h2>'
      +'<p>'+UI[lang].rmbody+'</p>'
      +'<a class="tla-rm-cta" href="'+BLOG+'" target="_blank" rel="noopener">'+esc(UI[lang].rmcta)+' <span aria-hidden="true">↗</span></a>'
    +'</div>'
    +'<div class="tla-rm-mark" aria-hidden="true">'+SIGIL_SVG+'</div>'
  +'</section>';
}
function renderLanding(s){
  var li=latestInfo(data);
  var h='<div class="tla-doc tla-landing">';
  h+='<div class="tla-hero"><div class="tla-hero-inner">';
  h+='<h1 class="tla-hero-title">The Living Arkham <span class="tla-beta">beta</span></h1>';
  h+='<p class="tla-hero-sub">'+esc(UI[lang].sub)+'</p>';
  h+='</div></div>';
  if(li){h+=verBanner(li);}
  h+=rmPanel();
  h+='<h2 class="tla-cards-h">'+esc(UI[lang].browse)+'</h2>';
  h+='<div class="tla-cards">';
  data.sections.forEach(function(s2,si){
    if(s2.kind==='intro')return;
    var news=s2.kind==='whatsnew';
    var n=sectionEntries(s2).length;
    var num=news?'✦':(s2.num||'•');
    var meta=news?(UI[lang].newver+' · v'+s2.ver.v):(n+' '+UI[lang].entries);
    h+='<button class="tla-card'+(news?' news':'')+'" type="button" data-si="'+si+'">';
    h+='<span class="tla-card-top"><span class="tla-card-num">'+num+'</span><span class="tla-card-title">'+esc(s2.title)+'</span></span>';
    h+='<span class="tla-card-meta">'+esc(meta)+'</span></button>';
  });
  h+='</div>';
  if(s.intro&&s.intro.length){
    h+='<section class="tla-landing-about"><h2>'+esc(UI[lang].about)+'</h2><div class="tla-lead">'+blocksHTML(s.intro)+'</div></section>';
  }
  h+='</div>';
  elMain.innerHTML=h; elToc.innerHTML=''; elMain.scrollTop=0;
}

/* ---------- TOC (right) ---------- */
function buildToc(s,ents){
  if(!ents.length){elToc.innerHTML=''; return;}
  var h='<h4>'+UI[lang].onthispage+'</h4>';
  ents.forEach(function(e){h+='<a href="#'+lang+'/'+esc(e.id)+'" data-eid="'+esc(e.id)+'" style="'+(e.sub?'padding-left:18px;':'')+'">'+titleHTML(e)+'</a>';});
  elToc.innerHTML=h;
}
function markNav(sid){
  [].forEach.call(elNav.querySelectorAll('.tla-nav-btn'),function(b){b.classList.remove('active'); b.removeAttribute('aria-current');});
  [].forEach.call(elNav.querySelectorAll('.tla-nav-sec'),function(d){d.classList.remove('open');});
  var sec=document.getElementById('navsec-'+sid);
  if(sec){sec.classList.add('open'); var b=sec.querySelector('.tla-nav-btn'); if(b){b.classList.add('active'); b.setAttribute('aria-current','true'); b.scrollIntoView({block:'nearest'});}}
}

/* ---------- scroll spy ---------- */
var spyRAF=null;
function spy(){
  if(spyRAF)return; spyRAF=requestAnimationFrame(function(){spyRAF=null;
    var arts=elMain.querySelectorAll('.tla-entry'); var top=140,cur=null;
    for(var i=0;i<arts.length;i++){var r=arts[i].getBoundingClientRect(); if(r.top<=top+40)cur=arts[i].id.slice(2); else break;}
    [].forEach.call(elToc.querySelectorAll('a'),function(a){a.classList.toggle('on',a.getAttribute('data-eid')===cur);});
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
  elSOpen.setAttribute('aria-label',UI[L].searchtitle);
  elSCancel.textContent=UI[L].cancel;
  elSModal.setAttribute('aria-label',UI[L].searchtitle);
  document.getElementById('tla-searchhint').innerHTML=hintHTML(L);
  document.getElementById('tla-foot-src').innerHTML=UI[L].footsrc;
  document.getElementById('tla-foot-by').innerHTML=UI[L].footby;
  applyThemeLabel();
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
  glossFilter='all';
  var m=(location.hash||'').replace(/^#/,'').split('/');
  var L=(m[0]==='en'||m[0]==='es')?m[0]:lang;
  if(L!==lang)applyLang(L);
  var target=m[1], f=target?findEntry(L,target):null;
  if(f){render(f.sid,f.eid,lastFlash);} else {render(data.sections[0].id,null,false);}
  lastFlash=false; closeResults();
  if(!firstRoute){try{elMain.focus({preventScroll:true});}catch(e){}} firstRoute=false;
}
function setLang(L){
  if(L===lang)return;
  var g=GRIM[L], s=curSec, m=null;
  if(s){
    if(s.num){m=g.sections.filter(function(x){return x.num===s.num;})[0];}
    else{m=g.sections.filter(function(x){return x.kind===s.kind;})[0];}   // intro / novedades / numberless
  }
  setHash(L,(m||g.sections[0]).id,false);
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
function searchOpen(){return !elSModal.hidden;}
function openSearch(){
  elSModal.hidden=false;
  try{elQ.focus();elQ.select();}catch(e){}
  if(elQ.value.trim().length>=2)search(elQ.value);
}
function closeSearch(){
  elSModal.hidden=true; elQ.value=''; closeResults();
  try{elSOpen.focus();}catch(e){}
}
function hintHTML(L){var u=UI[L];
  return '<span><kbd>↑</kbd><kbd>↓</kbd> '+u.khnav+'</span><span><kbd>↵</kbd> '+u.khopen+'</span><span><kbd>Esc</kbd> '+u.khclose+'</span>';
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
    var cd=e.target.closest('.tla-card'); if(cd){navigate(data.sections[+cd.getAttribute('data-si')].id,false); return;}
    var go=e.target.closest('[data-go]'); if(go){navigate(go.getAttribute('data-go'),false); return;}
    var wc=e.target.closest('.tla-wncard'); if(wc){gotoTarget(wc.getAttribute('data-eid'),true); return;}
    var az=e.target.closest('.tla-azbtn'); if(az){setGlossFilter(az.getAttribute('data-az')); return;}
    var x=e.target.closest('.xref'); if(x){e.preventDefault(); gotoTarget(x.getAttribute('data-t'),true); return;}
    var a=e.target.closest('.anchor'); if(a){e.preventDefault(); gotoTarget(a.getAttribute('href').split('/')[1],true); return;}
    var img=e.target.closest('.tla-fig img'); if(img){lightbox(img.src);}
  });
  elToc.addEventListener('click',function(e){var a=e.target.closest('[data-eid]'); if(a){e.preventDefault(); gotoTarget(a.getAttribute('data-eid'),true);}});
  elRes.addEventListener('click',function(e){var r=e.target.closest('.tla-res'); if(r){gotoTarget(r.getAttribute('data-eid'),true); closeSearch();}});
  elSOpen.addEventListener('click',openSearch);
  elSCancel.addEventListener('click',closeSearch);
  elSModal.addEventListener('click',function(e){if(e.target===elSModal)closeSearch();});
  document.querySelector('.tla-lang').addEventListener('click',function(e){var b=e.target.closest('button'); if(b)setLang(b.getAttribute('data-l'));});
  elTheme.addEventListener('click',toggleTheme);
  document.getElementById('tla-home').addEventListener('click',function(e){e.preventDefault(); navigate(data.sections[0].id,false);});
  document.getElementById('tla-burger').addEventListener('click',function(){elNav.classList.contains('on')?closeNav():openNav();});
  document.getElementById('tla-scrim').addEventListener('click',closeNav);

  var qTimer=null;
  elQ.addEventListener('input',function(){clearTimeout(qTimer); qTimer=setTimeout(function(){search(elQ.value);},110);});
  elQ.addEventListener('focus',function(){if(elQ.value.trim().length>=2)search(elQ.value);});
  elQ.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){e.preventDefault();moveSel(1);}
    else if(e.key==='ArrowUp'){e.preventDefault();moveSel(-1);}
    else if(e.key==='Enter'){var items=elRes.querySelectorAll('.tla-res'); var pick=items[resSel<0?0:resSel]; if(pick){gotoTarget(pick.getAttribute('data-eid'),true);closeSearch();}}
    else if(e.key==='Escape'){closeSearch();}
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='/'&&!searchOpen()&&!/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)){e.preventDefault();openSearch();}
    else if(e.key==='Escape'&&searchOpen()){closeSearch();}
  });
  elMain.addEventListener('scroll',spy,{passive:true});
  window.addEventListener('hashchange',route);

  var lb=document.getElementById('tla-lb');
  lb.addEventListener('click',function(){this.classList.remove('on');});
}
function lightbox(src){var lb=document.getElementById('tla-lb'); lb.querySelector('img').src=src; lb.classList.add('on');}

/* ---------- boot ---------- */
function boot(){
  Promise.all([
    fetch('data/grimoire_es.json').then(function(r){return r.json();}),
    fetch('data/grimoire_en.json').then(function(r){return r.json();}),
    fetch('assets/icons/icons.json').then(function(r){return r.json();})
  ]).then(function(res){
    GRIM.es=res[0]; GRIM.en=res[1]; ICONS=res[2];
    normalizeData(GRIM.es); normalizeData(GRIM.en);
    var sg=document.querySelector('.tla-brand .tla-sigil'); SIGIL_SVG=sg?sg.outerHTML:'';
    data=GRIM[lang];
    buildIndex();
    applyLang(lang);
    wireEvents();
    route();
  }).catch(function(err){
    elMain.innerHTML='<div class="tla-doc"><div class="tla-note"><b>'+UI[lang].loaderr+'</b><br>'+esc(String(err))+'</div></div>';
    console.error('The Living Arkham:',err);
  });
}
boot();
})();
