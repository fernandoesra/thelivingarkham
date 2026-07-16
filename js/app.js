/* ============================================================
   The Living Arkham — app logic

   Knows no language. Everything language-specific is fetched at runtime:
     data/languages.json     which languages exist (built by tools/ingest.py)
     langs/<code>/ui.json    that language's interface strings + icon labels
     data/grimoire_<code>.json  its content
   Adding a language is therefore a data change, never a change to this file.
   ============================================================ */
(function () {
"use strict";

/* The only strings that can't be fetched: the ones needed to report that a
   fetch failed. Everything else lives in the packs. */
var BOOT = {
  loaderr: "Could not load the grimoire.",
  retry: "Reload"
};

var GRIM = {},        // code -> grimoire data (loaded on demand)
    PACKS = {},       // code -> ui.json
    REG = null,       // the language registry
    LANGS = [];       // registry entries, in display order
var BLOG='https://rinconmiskatonic.org/', SIGIL_SVG='';

/* ---------- i18n ---------- */
/* A string is looked up in the active language, then along its fallback chain,
   then the site default. A pack may therefore be translated a little at a time:
   whatever is missing shows in another language instead of breaking the page. */
function chainOf(code){
  var seen={}, out=[], c=code;
  while(c && !seen[c]){ seen[c]=1; out.push(c); c=(PACKS[c]&&PACKS[c].fallback)||null; }
  if(REG && !seen[REG.default]) out.push(REG.default);
  return out;
}
function pick(code, group, key){
  var ch=chainOf(code);
  for(var i=0;i<ch.length;i++){
    var p=PACKS[ch[i]];
    if(p && p[group] && p[group][key]!=null && p[group][key]!=='') return p[group][key];
  }
  return null;
}
function t(key){ var v=pick(lang,'strings',key); return v==null?key:v; }
function iconLabel(name){ var v=pick(lang,'icons',name); return v==null?name:v; }
function uiOf(code, key, dflt){
  var ch=chainOf(code);
  for(var i=0;i<ch.length;i++){ var p=PACKS[ch[i]]; if(p && p[key]!=null) return p[key]; }
  return dflt;
}
/* Dates come from the pack's own month names, not from Intl: the browser's CLDR
   data varies by version and doesn't match the abbreviations the book uses. */
function fmtDate(iso){
  if(!iso)return '';
  var p=String(iso).split('-'); if(p.length<3)return iso;
  var months=uiOf(lang,'months',null);
  var mon=(months&&months[(+p[1])-1])||p[1];
  var pat=uiOf(lang,'datePattern','{d} {mon} {y}');
  return pat.replace('{d}',+p[2]).replace('{mon}',mon).replace('{y}',p[0]);
}
/* The newest edition that actually recorded changes — not necessarily the newest
   edition. A quiet reprint must not hide the whole history behind it. */
function latestInfo(g){
  if(!g.versions||g.versions.length<2||!g.whatsnew)return null;
  for(var i=g.versions.length-1;i>=0;i--){
    if(g.whatsnew[g.versions[i].v])return g.versions[i];
  }
  return null;
}
var root=document.getElementById('tla-root');
var elNav=document.getElementById('tla-nav'), elMain=document.getElementById('tla-main'),
    elToc=document.getElementById('tla-toc'), elQ=document.getElementById('tla-q'),
    elRes=document.getElementById('tla-results'), elLive=document.getElementById('tla-live'),
    elTheme=document.getElementById('tla-theme'),
    elSModal=document.getElementById('tla-searchmodal'),
    elSOpen=document.getElementById('tla-search-open'),
    elSCancel=document.getElementById('tla-search-cancel'),
    elFigModal=document.getElementById('tla-figmodal'),
    elFigHead=document.getElementById('tla-figmodal-h'),
    elFigBody=document.getElementById('tla-figmodal-body'),
    elFigClose=document.getElementById('tla-figmodal-close'),
    elLb=document.getElementById('tla-lb');
var lastFigBtn=null;
/* set by boot() from the registry — never hardcoded to any language */
var lang='', data=null, curSec=null, searchIndex={}, resSel=-1, glossFilter='all', firstRoute=true;

/* ---------- helpers ---------- */
function esc(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function announce(msg){if(elLive){elLive.textContent=''; setTimeout(function(){elLive.textContent=msg;},40);}}
/* Labels come from a pack, so they are escaped like any other authored text:
   a label containing a quote would otherwise break out of the attribute. */
function iconHTML(name){return '<i class="ico ico-'+esc(name)+'" title="'+esc(iconLabel(name))+'"></i>';}
function runsHTML(runs,suppressNew){
  var h='';
  for(var i=0;i<runs.length;i++){var r=runs[i];
    if(r.kind==='icon'){h+=iconHTML(r.name); continue;}
    if(r.kind==='pageref'){h+='<span class="tla-pageref" title="'+esc(t('origpage')+' '+r.n)+'">('+esc(t('origpage'))+' '+esc(r.n)+')</span>'; continue;}
    var inner=(r.kind==='link')?'<a class="xref" data-t="'+esc(r.target)+'">'+wrap(esc(r.t),r)+'</a>':wrap(esc(r.t),r);
    if(r.v && !suppressNew){inner='<span class="tla-new" title="'+esc(t('addedin')+r.v)+'">'+inner+'</span>';}
    h+=inner;
  }
  return h;
}
function wrap(s,r){if(r.bold)s='<strong>'+s+'</strong>'; if(r.italic)s='<em>'+s+'</em>'; return s;}
/* suppressNew: inside an entry that is itself brand new, every run would be
   flagged as added — which says nothing. The entry already carries its own
   "New vX" badge, so the per-run diff marks are suppressed there (the title
   does the same via titleHTML). */
function blocksHTML(blocks,suppressNew){
  var h='',i=0;
  while(i<blocks.length){
    var b=blocks[i];
    if(b.type==='bullet'){
      h+='<ul class="tla-bul">';
      while(i<blocks.length && blocks[i].type==='bullet'){
        h+='<li class="'+(blocks[i].level===2?'l2':'l1')+'">'+runsHTML(blocks[i].runs,suppressNew)+'</li>'; i++;
      }
      h+='</ul>';
    } else if(b.type==='sym'){ h+='<div class="tla-sym">'+runsHTML(b.runs,suppressNew)+'</div>'; i++; }
    else { h+='<p class="tla-p">'+runsHTML(b.runs,suppressNew)+'</p>'+faqLink(plainOfRuns(b.runs)); i++; }
  }
  return h;
}
/* The PDF shows a QR code to the retired-FAQ document after a sentence ending in
   a colon; render a real link instead. Which sentence that is depends on the
   language, so the pack says (ui.json -> "faqAnchor"). No anchor, no link. */
function faqLink(txt){
  var s=(txt||'').trim(), anchor=uiOf(lang,'faqAnchor',null);
  if(!anchor || !t('faqurl')) return '';
  var re; try{ re=new RegExp(anchor,'i'); }catch(e){ return ''; }
  if(!re.test(s) || !/[:：]\s*$/.test(s)) return '';
  return '<a class="tla-extlink" href="'+t('faqurl')+'" target="_blank" rel="noopener">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg>'
    +esc(t('faqlabel'))+'</a>';
}
function plainOfRuns(runs,L){var s='';for(var i=0;i<runs.length;i++){s+=runs[i].kind==='text'||runs[i].kind==='link'?runs[i].t:(' '+(pick(L||lang,'icons',runs[i].name)||'')+' ');}return s;}
function plainOfBlocks(blocks,L){return blocks.map(function(b){return plainOfRuns(b.runs,L);}).join(' ');}
function titleHTML(e){return e.titleRuns?runsHTML(e.titleRuns,true):esc(e.title);}
/* An entry's history, as the data actually records it:
     addedIn    the edition it first appeared in
     changedIn  every later edition that rewrote part of it
   A badge is only shown for the newest edition — that is the "what changed"
   signal. The full provenance goes in a quieter line underneath. */
function latestV(){return (data.versions&&data.versions.length>1)?data.versions[data.versions.length-1].v:null;}
function isNewIn(e,v){return e.addedIn===v;}
function isChangedIn(e,v){return !!(e.changedIn&&e.changedIn.indexOf(v)>=0);}
function verBadge(e){
  var v=latestV(); if(!v)return '';
  if(isNewIn(e,v))return '<span class="tla-vbadge new" title="'+esc(t('addedin')+v)+'">'+esc(t('newbadge'))+' v'+esc(v)+'</span>';
  if(isChangedIn(e,v))return '<span class="tla-vbadge upd" title="'+esc(t('updatedin')+v)+'">'+esc(t('updbadge'))+' v'+esc(v)+'</span>';
  return '';
}
/* "Added in v1.0 · rewritten in v1.1" — shown on any entry with a history worth
   telling, so you can always see which edition brought which entry. */
function verProvenance(e){
  if(!data.versions||data.versions.length<2)return '';
  var bits=[];
  if(e.addedIn)bits.push(esc(t('addedinv').replace('{v}',e.addedIn)));
  if(e.changedIn&&e.changedIn.length)
    bits.push(esc(t('changedinv').replace('{v}',e.changedIn.map(function(v){return 'v'+v;}).join(', '))));
  if(!bits.length)return '';
  return '<p class="tla-prov">'+bits.join(' · ')+'</p>';
}
/* montage figures (example card-art resources) shown inside a glossary entry,
   with an "i" that reveals the textual alternative (card data). */
function figSrc(f){  // credit band: original page + document version
  var v=(data.versions&&data.versions.length)?data.versions[data.versions.length-1].v:'';
  var p=(f.srcpage!=null)?(' '+f.srcpage):'';
  return t('fig')+p+(v?(' · v'+v):'');
}
function figuresHTML(e,idbase){
  if(!e.figures||!e.figures.length)return '';
  var h='';
  e.figures.forEach(function(f,i){
    var fid='fig-'+idbase+'-'+i;
    var wh=f.w?(' width="'+f.w+'" height="'+f.h+'"'):'';
    h+='<figure class="tla-montage">';
    h+='<div class="tla-montage-frame">';
    h+='<img class="tla-montage-img" loading="lazy" src="assets/img/'+esc(f.file)+'" alt="'+esc(f.alt||t('figalt'))+'"'+wh+'>';
    /* aria-controls names the dialog this opens; data-src names the hidden block
       the dialog is filled from. They are different elements. */
    if(f.info)h+='<button class="tla-montage-i" type="button" aria-haspopup="dialog" aria-controls="tla-figmodal" data-src="'+fid+'" aria-label="'+esc(t('figinfo'))+'" title="'+esc(t('figinfo'))+'">i</button>';
    h+='<div class="tla-montage-cap">'+esc(figSrc(f))+'</div>';
    h+='</div>';
    if(f.info)h+='<div class="tla-montage-info" id="'+fid+'" hidden>'+f.info+'</div>';
    h+='</figure>';
  });
  return h;
}
function openFigInfo(btn){
  var src=document.getElementById(btn.getAttribute('data-src')); if(!src)return;
  lastFigBtn=btn;
  elFigHead.textContent=t('figdata');
  elFigBody.innerHTML=src.innerHTML;
  elFigModal.hidden=false;
  try{elFigClose.focus();}catch(e){}
}
function figInfoOpen(){return !elFigModal.hidden;}
function closeFigInfo(){
  elFigModal.hidden=true; elFigBody.innerHTML='';
  try{if(lastFigBtn)lastFigBtn.focus();}catch(e){}
  lastFigBtn=null;
}

/* ---------- theme ---------- */
function currentTheme(){return document.documentElement.getAttribute('data-theme')==='light'?'light':'dark';}
function applyThemeLabel(){var th=currentTheme(); if(elTheme)elTheme.setAttribute('aria-label', th==='dark'?t('tolight'):t('todark'));}
function setTheme(th){document.documentElement.setAttribute('data-theme',th); try{localStorage.setItem('tla-theme',th);}catch(e){} applyThemeLabel();}
function toggleTheme(){setTheme(currentTheme()==='dark'?'light':'dark');}

/* ---------- build search index ---------- */
/* The index is built per language and stores plain text, so the language must be
   passed in rather than read from the active one: an index built while another
   language happened to be active would carry that language's icon labels. */
function buildIndex(L){
  var arr=[]; GRIM[L].sections.forEach(function(s){
    if(s.intro&&s.intro.length){arr.push({sid:s.id,eid:s.id,title:s.title,sec:s.title,num:s.num,text:plainOfBlocks(s.intro,L),isSec:true});}
    (s.entries||[]).forEach(function(e){arr.push({sid:s.id,eid:e.id,title:e.title,titleRuns:e.titleRuns,sec:s.title,num:s.num,text:plainOfBlocks(e.blocks,L)});});
  });
  searchIndex[L]=arr;
}

/* ---------- version history helpers ---------- */
/* "What's New" is not a chapter of the book: it is derived from the version
   history, so the app inserts it. Its id stays 'novedades' in every language —
   it is a permalink that has been shared, not user-visible prose. */
function normalizeData(g){
  var li=latestInfo(g);
  if(li && !g.sections.some(function(x){return x.id==='novedades';})){
    g.sections.splice(1,0,{num:'',key:'whatsnew',id:'novedades',kind:'whatsnew',
      title:pick(g.lang,'strings','news')||'What\'s New',ver:li,intro:[],entries:[],figures:[]});
  }
}
/* the nav badge counts what the newest edition brought */
function wnCount(s){var wn=data.whatsnew&&data.whatsnew[s.ver.v]; return wn?(wn['new'].length+wn.updated.length):0;}

/* ---------- entries / filtering ---------- */
function sectionEntries(s){return s.entries||[];}
function stripAccents(c){ return c.normalize? c.normalize('NFD').replace(/[̀-ͯ]/g,'') : c; }
/* Which letter an entry files under. A language's own letters (ES: Ñ) stay
   themselves; an accented form of a letter it already has (ES: Ú) files under
   the plain one, the way a dictionary does. */
function entryLetter(e){
  var c=(e.title||'').replace(/[“"'¿¡().]/g,'').charAt(0).toUpperCase();
  if(!c) return '#';
  if(/[0-9]/.test(c)) return '#';
  var az=uiOf(lang,'alphabet','')||'';
  if(az.indexOf(c)>=0) return c;
  var f=stripAccents(c);
  if(!az || az.indexOf(f)>=0) return f;
  return c;                       // a letter the pack didn't predict: keep it
}
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
    var num=news?'<span class="tla-nav-num"><i class="tla-eldersign" aria-hidden="true"></i></span>'
                :(s.num?('<span class="tla-nav-num">'+esc(s.num)+'</span>'):'<span class="tla-nav-num">•</span>');
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
/* The order of the buttons: the pack's alphabet, then any letter it didn't
   predict, then '#'. Never the other way round — a letter that is present but
   unlisted must still get a button, or its entries are counted yet unreachable. */
function azOrder(present){
  var az=(uiOf(lang,'alphabet','')||'').split('');
  var order=az.filter(function(c){return present[c];});
  var extra=Object.keys(present).filter(function(c){return c!=='#' && az.indexOf(c)<0;}).sort();
  if(extra.length && az.length){
    try{console.warn('The Living Arkham: langs/'+lang+'/ui.json "alphabet" does not list '+
      extra.join(', ')+' — showing them at the end. Add them if they belong.');}catch(e){}
  }
  order=order.concat(extra);
  if(present['#'])order.push('#');
  return order;
}
function azFilterBar(s){
  var present={}; sectionEntries(s).forEach(function(e){present[entryLetter(e)]=1;});
  var order=azOrder(present);
  var total=sectionEntries(s).length, shown=visibleEntries(s).length;
  var h='<div class="tla-azfilter"><div class="tla-azlabel">'+t('filterby')+'</div><div class="tla-azrow">';
  h+='<button class="tla-azbtn all'+(glossFilter==='all'?' active':'')+'" type="button" data-az="all" aria-pressed="'+(glossFilter==='all')+'">'+t('all')+'</button>';
  order.forEach(function(c){ h+='<button class="tla-azbtn'+(glossFilter===c?' active':'')+'" type="button" data-az="'+esc(c)+'" aria-pressed="'+(glossFilter===c)+'">'+esc(c)+'</button>'; });
  h+='<span class="tla-azcount">'+(glossFilter==='all'?total:shown+' '+t('of')+' '+total)+' '+t('entries')+'</span>';
  h+='</div></div>';
  return h;
}
function setGlossFilter(v){
  glossFilter=v; render(curSec.id,null,false); elMain.scrollTop=0;
  var n=visibleEntries(curSec).length;
  announce((v==='all'?t('all'):v)+': '+n+' '+t('entries'));
}

/* ---------- render section ---------- */
function render(sid,eid,flash){
  var s=data.sections.filter(function(x){return x.id===sid;})[0]; if(!s)s=data.sections[0];
  curSec=s;
  if(s.kind==='whatsnew'){renderWhatsNew(); markNav(sid); return;}
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
      h+='<figure class="tla-fig"><img loading="lazy" src="assets/img/'+esc(f.file)+'" alt=""><figcaption>'+t('fig')+' '+f.page+'</figcaption></figure>';});
    h+='</div>';
  }
  if(s.kind==='glossary'){h+=azFilterBar(s);}
  var lv=latestV();
  ents.forEach(function(e){
    /* An entry that is wholly new needs no per-word diff marks — the badge
       already says so. One that was rewritten does: the marks are the point. */
    var brandNew=lv&&isNewIn(e,lv);
    /* h2: an entry sits directly under the chapter's h1. Jumping straight to h3
       would leave a hole in the outline a screen reader navigates by. */
    h+='<article class="tla-entry'+(e.sub?' sub':'')+(brandNew?' is-new':'')+(lv&&isChangedIn(e,lv)?' is-upd':'')+'" id="e-'+esc(e.id)+'">';
    h+='<h2>'+titleHTML(e)+verBadge(e)+'<a class="anchor" href="#'+lang+'/'+esc(e.id)+'" title="'+esc(t('jump'))+'" aria-label="'+esc(t('jump'))+'">§</a></h2>';
    h+=blocksHTML(e.blocks,brandNew);
    h+=verProvenance(e);
    h+=figuresHTML(e,esc(e.id));
    h+='</article>';
  });
  h+='</div>';
  elMain.innerHTML=h;
  syncStickyHeight();          // before any scroll-to, so the target clears the toolbar
  buildToc(s,ents);
  markNav(sid);
  if(eid){var el=document.getElementById('e-'+eid); if(el){el.scrollIntoView({block:'start'}); if(flash){el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}}}
  else{elMain.scrollTop=0;}
}
function verBanner(li){
  return '<button class="tla-verbanner" type="button" data-go="novedades">'
    +'<i class="tla-eldersign tla-vb-star" aria-hidden="true"></i>'
    +'<span class="tla-vb-main"><span class="tla-vb-t">'+t('newver')+' · v'+li.v+'</span>'
    +'<span class="tla-vb-d">'+t('released')+' '+fmtDate(li.date)+'</span></span>'
    +'<span class="tla-vb-cta">'+t('seenews')+' →</span></button>';
}
/* Which edition the What's New page is showing. Defaults to the newest — the
   book is a living document, so "what just changed" is the question people
   arrive with — but every edition stays reachable. */
var wnPick=null;
function wnVersions(){
  /* newest first: history reads backwards */
  return (data.versions||[]).filter(function(v){return data.whatsnew&&data.whatsnew[v.v];}).reverse();
}
function renderWhatsNew(){
  var vs=wnVersions();
  if(!vs.length){elMain.innerHTML=''; elToc.innerHTML=''; return;}
  var cur=null;
  for(var i=0;i<vs.length;i++){if(vs[i].v===wnPick)cur=vs[i];}
  if(!cur)cur=vs[0];
  var wn=data.whatsnew[cur.v];

  var h='<div class="tla-doc">';
  h+='<div class="tla-crumb">The Living Arkham</div>';
  h+='<h1 class="tla-h1">'+esc(t('news'))+'</h1><div class="tla-rule"></div>';

  // the whole history, always — one chip per edition, newest first
  h+='<div class="tla-vertabs" role="group" aria-label="'+esc(t('history'))+'">';
  vs.forEach(function(v){
    var n=data.whatsnew[v.v], count=n['new'].length+n.updated.length;
    h+='<button class="tla-vertab'+(v.v===cur.v?' active':'')+'" type="button" data-wnv="'+esc(v.v)+'"'
      +' aria-pressed="'+(v.v===cur.v)+'">'
      +'<span class="tla-vertab-v">v'+esc(v.v)+'</span>'
      +'<span class="tla-vertab-d">'+esc(fmtDate(v.date))+'</span>'
      +'<span class="tla-vertab-n">'+count+'</span></button>';
  });
  var first=(data.versions||[])[0];
  if(first && !data.whatsnew[first.v]){
    h+='<span class="tla-vertab is-origin">'+esc(t('firstedition').replace('{v}',first.v))
      +' · '+esc(fmtDate(first.date))+'</span>';
  }
  h+='</div>';

  h+='<div class="tla-note">'+esc(t('newsintro'))+'</div>';
  if(wn['new'].length){h+='<h2 class="tla-wnh"><span class="tla-vbadge new">'+esc(t('newbadge'))+'</span> '+esc(t('newentries'))+' <span class="tla-wncount">'+wn['new'].length+'</span></h2>'
    +'<p class="tla-wnhelp">'+esc(t('newhelp').replace('{v}',cur.v))+'</p>'+wnList(wn['new'],'new');}
  if(wn.updated.length){h+='<h2 class="tla-wnh"><span class="tla-vbadge upd">'+esc(t('updbadge'))+'</span> '+esc(t('updentries'))+' <span class="tla-wncount">'+wn.updated.length+'</span></h2>'
    +'<p class="tla-wnhelp">'+esc(t('updhelp').replace('{v}',cur.v))+'</p>'+wnList(wn.updated,'upd');}
  h+='</div>';
  elMain.innerHTML=h; elToc.innerHTML=''; elMain.scrollTop=0;
}
function wnList(items,cls){
  var h='<div class="tla-wngrid">';
  items.forEach(function(it){
    // a whole chapter can change too — the FAQ gains answers in its own lead text
    var where=it.chapter?esc(t('chapter')):((it.num?esc(it.num)+' · ':'')+esc(it.sec));
    h+='<button class="tla-wncard '+cls+(it.chapter?' is-chapter':'')+'" type="button" data-eid="'+esc(it.id)+'">'
      +'<span class="tla-wntitle">'+esc(it.title)+'</span>'
      +'<span class="tla-wnsec">'+where+'</span></button>';});
  return h+'</div>';
}
function rmPanel(){
  return '<section class="tla-rm">'
    +'<div class="tla-rm-body">'
      +'<h2 class="tla-rm-title">'+esc(t('rmtitle'))+'</h2>'
      +'<p>'+t('rmbody')+'</p>'
      +'<a class="tla-rm-cta" href="'+BLOG+'" target="_blank" rel="noopener">'+esc(t('rmcta'))+' <span aria-hidden="true">↗</span></a>'
    +'</div>'
    +'<div class="tla-rm-mark" aria-hidden="true">'+SIGIL_SVG+'</div>'
  +'</section>';
}
function renderLanding(s){
  var li=latestInfo(data);
  var h='<div class="tla-doc tla-landing">';
  h+='<div class="tla-hero"><div class="tla-hero-inner">';
  h+='<h1 class="tla-hero-title">The Living Arkham <span class="tla-beta">beta</span></h1>';
  h+='<p class="tla-hero-sub">'+esc(t('sub'))+'</p>';
  h+='</div></div>';
  if(li){h+=verBanner(li);}
  h+=rmPanel();
  h+='<h2 class="tla-cards-h">'+esc(t('browse'))+'</h2>';
  h+='<div class="tla-cards">';
  data.sections.forEach(function(s2,si){
    if(s2.kind==='intro')return;
    var news=s2.kind==='whatsnew';
    var n=sectionEntries(s2).length;
    var num=news?'<i class="tla-eldersign" aria-hidden="true"></i>':esc(s2.num||'•');
    var meta=news?(t('newver')+' · v'+s2.ver.v):(n+' '+t('entries'));
    h+='<button class="tla-card'+(news?' news':'')+'" type="button" data-si="'+si+'">';
    h+='<span class="tla-card-top"><span class="tla-card-num">'+num+'</span><span class="tla-card-title">'+esc(s2.title)+'</span></span>';
    h+='<span class="tla-card-meta">'+esc(meta)+'</span></button>';
  });
  h+='</div>';
  if(s.intro&&s.intro.length){
    h+='<section class="tla-landing-about"><h2>'+esc(t('about'))+'</h2><div class="tla-lead">'+blocksHTML(s.intro)+'</div></section>';
  }
  h+='</div>';
  elMain.innerHTML=h; elToc.innerHTML=''; elMain.scrollTop=0;
}

/* ---------- TOC (right) ---------- */
function buildToc(s,ents){
  if(!ents.length){elToc.innerHTML=''; return;}
  var h='<h2 class="tla-toc-h">'+esc(t('onthispage'))+'</h2>';
  ents.forEach(function(e){h+='<a href="#'+lang+'/'+esc(e.id)+'" data-eid="'+esc(e.id)+'" style="'+(e.sub?'padding-left:18px;':'')+'">'+titleHTML(e)+'</a>';});
  elToc.innerHTML=h;
}
/* Scroll a child into view inside its own scroller, by hand.
   NOT Element.scrollIntoView(): that also moves the browser's sequential focus
   navigation starting point, so the next Tab would resume from the nav instead
   of the top of the page — which silently makes the skip link, and the whole
   header, unreachable by Tab. */
/* The A-Z toolbar is sticky, so anything scrolled to must clear it. Its height
   depends on the language's alphabet and on how far the row wraps, so it is
   measured rather than guessed — a fixed value hid entry titles behind it. */
function syncStickyHeight(){
  var bar=elMain.querySelector('.tla-azfilter');
  elMain.style.setProperty('--sticky-h',(bar?bar.offsetHeight:0)+'px');
}
function keepInView(el,box){
  var e=el.getBoundingClientRect(), b=box.getBoundingClientRect();
  if(e.top<b.top) box.scrollTop-=(b.top-e.top);
  else if(e.bottom>b.bottom) box.scrollTop+=(e.bottom-b.bottom);
}
function markNav(sid){
  [].forEach.call(elNav.querySelectorAll('.tla-nav-btn'),function(b){b.classList.remove('active'); b.removeAttribute('aria-current');});
  [].forEach.call(elNav.querySelectorAll('.tla-nav-sec'),function(d){d.classList.remove('open');});
  var sec=document.getElementById('navsec-'+sid);
  if(sec){sec.classList.add('open'); var b=sec.querySelector('.tla-nav-btn');
    if(b){b.classList.add('active'); b.setAttribute('aria-current','true'); keepInView(b,elNav);}}
}

/* ---------- scroll spy ---------- */
var spyRAF=null;
function spy(){
  if(spyRAF)return; spyRAF=requestAnimationFrame(function(){spyRAF=null;
    var arts=elMain.querySelectorAll('.tla-entry'); var top=140,cur=null;
    for(var i=0;i<arts.length;i++){var r=arts[i].getBoundingClientRect(); if(r.top<=top+40)cur=arts[i].id.slice(2); else break;}
    [].forEach.call(elToc.querySelectorAll('a'),function(a){a.classList.toggle('on',a.getAttribute('data-eid')===cur);});
    syncHash(cur);
  });
}
/* Keep the URL pointing at the entry you're actually reading, so the browser Back
   button returns you there. replaceState does NOT fire hashchange, so it never
   re-renders — it only rewrites the current history entry's target. */
function syncHash(cur){
  if(!cur||!curSec||curSec.kind==='intro'||curSec.kind==='whatsnew')return;
  var nh='#'+lang+'/'+cur;
  if(location.hash!==nh){try{history.replaceState(history.state,'',nh);}catch(e){}}
}

/* ---------- routing (URL hash = single source of truth) ---------- */
var lastFlash=false;
function findEntry(L,eid){
  var g=GRIM[L]; for(var i=0;i<g.sections.length;i++){var s=g.sections[i]; if(s.id===eid)return{sid:s.id,eid:null};
    for(var j=0;j<(s.entries||[]).length;j++){if(s.entries[j].id===eid)return{sid:s.id,eid:eid};}}
  return null;
}
function regOf(L){for(var i=0;i<LANGS.length;i++){if(LANGS[i].code===L)return LANGS[i];}return null;}
function known(L){return !!regOf(L);}

/* The language switcher is built from the registry, so a new pack appears here
   by existing — there is no list of languages in the markup.
   The flag is decoration (alt=""): the label names the language, because a flag
   names a country and languages are not countries. A pack without a flag.svg
   simply shows its label. */
function buildLangBar(){
  var box=document.querySelector('.tla-lang'); if(!box)return;
  if(LANGS.length<2){box.hidden=true; return;}          // one language: no switcher
  box.hidden=false;
  box.innerHTML=LANGS.map(function(L){
    var flag=L.flag?'<img class="tla-flag" src="'+esc(L.flag)+'" alt="" width="20" height="14" aria-hidden="true">':'';
    return '<button type="button" data-l="'+esc(L.code)+'" lang="'+esc(L.code)+'"'+
           ' aria-pressed="'+(L.code===lang)+'">'+flag+
           '<span class="tla-lang-lb">'+esc(L.label||L.code.toUpperCase())+'</span>'+
           '<span class="tla-sr">'+esc(L.name)+'</span></button>';
  }).join('');
  // a flag that fails to load would otherwise sit there as an empty framed box
  [].forEach.call(box.querySelectorAll('.tla-flag'),function(img){
    img.addEventListener('error',function(){img.remove();});
  });
}

/* Fill every element that declares a string key in the markup:
     data-i18n="key"            -> text content
     data-i18n-html="key"       -> inner HTML (strings that contain markup)
     data-i18n-attr="aria-label:key, title:key"  -> attributes */
function applyStaticStrings(){
  [].forEach.call(document.querySelectorAll('[data-i18n]'),function(el){
    el.textContent=t(el.getAttribute('data-i18n'));
  });
  [].forEach.call(document.querySelectorAll('[data-i18n-html]'),function(el){
    el.innerHTML=t(el.getAttribute('data-i18n-html'));
  });
  [].forEach.call(document.querySelectorAll('[data-i18n-attr]'),function(el){
    el.getAttribute('data-i18n-attr').split(',').forEach(function(pair){
      var kv=pair.split(':'); if(kv.length!==2)return;
      el.setAttribute(kv[0].trim(), t(kv[1].trim()));
    });
  });
}

function applyLang(L){
  lang=L; data=GRIM[L];
  wnPick=null;                        // editions are numbered per language
  var reg=regOf(L)||{};
  root.setAttribute('data-lang',L);
  document.documentElement.setAttribute('lang',L);
  document.documentElement.setAttribute('dir',reg.dir||'ltr');
  if(t('doctitle')!=='doctitle')document.title=t('doctitle');
  var md=document.querySelector('meta[name="description"]');
  if(md && t('docdesc')!=='docdesc')md.setAttribute('content',t('docdesc'));
  buildLangBar();
  applyStaticStrings();
  elQ.setAttribute('placeholder',t('searchph'));
  document.getElementById('tla-searchhint').innerHTML=hintHTML();
  var home=document.getElementById('tla-home');
  if(home)home.setAttribute('href','#'+L+'/'+(data.sections[0]&&data.sections[0].id||''));
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

/* The hash is the single source of truth. A language in it is honoured only if
   the registry knows it — an unknown code falls back to the current language
   rather than being read as an entry id. */
var routeSeq=0;
function route(){
  var m=(location.hash||'').replace(/^#/,'').split('/');
  var L=known(m[0])?m[0]:lang;
  var target=m[1];
  /* A language is fetched before it renders, so a second navigation can start
     while the first is still downloading. Only the newest one may paint. */
  var mine=++routeSeq;
  loadLang(L).then(function(){
    if(mine!==routeSeq)return;
    glossFilter='all';
    if(L!==lang||data!==GRIM[L])applyLang(L);
    var f=target?findEntry(L,target):null;
    if(f){render(f.sid,f.eid,lastFlash);} else {render(data.sections[0].id,null,false);}
    lastFlash=false; closeResults();
    if(!firstRoute){try{elMain.focus({preventScroll:true});}catch(e){}} firstRoute=false;
    try{localStorage.setItem('tla-lang',L);}catch(e){}
  }, function(err){ if(mine===routeSeq)fatal(err); });
}
/* Switching language keeps you on the same chapter. Chapters are matched by
   their shared `key`, not by their number or kind: a numberless chapter would
   otherwise match the first one of the same kind and quietly land elsewhere. */
function setLang(L){
  if(L===lang)return;
  loadLang(L).then(function(){
    var g=GRIM[L], s=curSec, m=null;
    if(s&&s.key)m=g.sections.filter(function(x){return x.key===s.key;})[0];
    if(!m&&s&&s.num)m=g.sections.filter(function(x){return x.num===s.num;})[0];
    setHash(L,(m||g.sections[0]).id,false);
  }, fatal);
}

/* ---------- SEARCH ---------- */
function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');}
function search(q){
  q=norm(q.trim()); if(q.length<2){closeResults();return;}
  var terms=q.split(/\s+/), arr=searchIndex[lang], out=[];
  for(var i=0;i<arr.length;i++){var it=arr[i]; var hayT=norm(it.title), hayX=norm(it.text);
    var score=0,ok=true;
    for(var ti=0;ti<terms.length;ti++){var tm=terms[ti];
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
  var out=esc(text);
  terms.forEach(function(tm){if(!tm)return; var re=new RegExp('('+tm.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig');
    out=out.replace(re,'<mark>$1</mark>');});
  return out;
}
function snippet(text,terms){
  var nt=norm(text),pos=-1; for(var i=0;i<terms.length;i++){var p=nt.indexOf(terms[i]); if(p>=0&&(pos<0||p<pos))pos=p;}
  if(pos<0)pos=0; var st=Math.max(0,pos-40); var frag=text.slice(st,st+160); if(st>0)frag='…'+frag; return frag;
}
function renderResults(list,terms){
  if(!list.length){elRes.innerHTML='<div class="tla-res-empty">'+esc(t('nores'))+'</div>'; elRes.classList.add('on'); resSel=-1; clearActiveDesc(); setExpanded(true); return;}
  /* Each option needs an id: the input keeps the focus, so the only way a screen
     reader learns which result is highlighted is aria-activedescendant. */
  var h=''; list.forEach(function(o,i){var it=o.it;
    h+='<div class="tla-res" role="option" id="tla-res-'+i+'" aria-selected="false" data-eid="'+esc(it.eid)+'" data-i="'+i+'">';
    h+='<div class="rt">'+(it.titleRuns?runsHTML(it.titleRuns):hl(it.title,terms))+'<span class="rs">'+(it.num?it.num+' · ':'')+esc(it.sec)+'</span></div>';
    h+='<div class="rx">'+hl(snippet(it.text,terms),terms)+'</div></div>';
  });
  elRes.innerHTML=h; elRes.classList.add('on'); resSel=-1; clearActiveDesc(); setExpanded(true);
}
/* The options are gone: stop pointing at one, or the attribute names a dead id. */
function clearActiveDesc(){elQ.removeAttribute('aria-activedescendant');}
function closeResults(){elRes.classList.remove('on'); elRes.innerHTML=''; resSel=-1; clearActiveDesc(); setExpanded(false);}
function setExpanded(v){elQ.setAttribute('aria-expanded',v?'true':'false');}
function moveSel(d){var items=elRes.querySelectorAll('.tla-res'); if(!items.length)return;
  resSel=(resSel+d+items.length)%items.length;
  [].forEach.call(items,function(x,i){
    x.classList.toggle('sel',i===resSel);
    x.setAttribute('aria-selected',i===resSel?'true':'false');
    if(i===resSel){keepInView(x,elRes); elQ.setAttribute('aria-activedescendant',x.id);}
  });
}
function searchOpen(){return !elSModal.hidden;}
var lastSearchSrc=null;
function openSearch(){
  lastSearchSrc=document.activeElement;   // '/' can be pressed from anywhere
  elSModal.hidden=false;
  try{elQ.focus();elQ.select();}catch(e){}
  if(elQ.value.trim().length>=2)search(elQ.value);
}
/* Focus goes back where it came from, not always to the header button: the
   dialog can be opened with '/' from anywhere on the page. */
function closeSearch(){
  elSModal.hidden=true; elQ.value=''; closeResults();
  var back=(lastSearchSrc&&document.contains(lastSearchSrc))?lastSearchSrc:elSOpen;
  lastSearchSrc=null;
  try{back.focus();}catch(e){}
}
function hintHTML(){
  return '<span><kbd>↑</kbd><kbd>↓</kbd> '+esc(t('khnav'))+'</span><span><kbd>↵</kbd> '+esc(t('khopen'))+'</span><span><kbd>Esc</kbd> '+esc(t('khclose'))+'</span>';
}

/* ---------- dialogs ---------- */
/* aria-modal tells a screen reader to ignore the page behind, but it does not
   move the Tab key: without this, Tab walks straight out of an open dialog and
   into the page you can no longer see. One trap serves all three dialogs. */
var FOCUSABLE='a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])';
function focusablesIn(box){
  return [].filter.call(box.querySelectorAll(FOCUSABLE),function(el){
    return el.offsetWidth>0||el.offsetHeight>0||el===document.activeElement;
  });
}
/* innermost last: search can open over the drawer, and the lightbox over the
   figure dialog. The mobile nav is included because it behaves like a dialog —
   it covers the page behind a scrim. */
function dialogs(){
  return [
    {box:elNav,      isOpen:navOpen,     close:function(){closeNav(); focusBurger();}},
    {box:elSModal,   isOpen:searchOpen,  close:closeSearch},
    {box:elFigModal, isOpen:figInfoOpen, close:closeFigInfo},
    {box:elLb,       isOpen:lbOpen,      close:closeLightbox}
  ];
}
function openDialog(){
  var ds=dialogs(), open=null;
  for(var i=0;i<ds.length;i++){if(ds[i].isOpen())open=ds[i];}   // last one wins
  return open;
}
function trapTab(e){
  var d=openDialog(); if(!d)return;
  var box=d.box, items=focusablesIn(box);
  if(box===elLb)items=[elLb.querySelector('.tla-lb-close')];
  if(!items.length){e.preventDefault(); return;}
  var first=items[0], last=items[items.length-1];
  if(!box.contains(document.activeElement)){e.preventDefault(); first.focus(); return;}
  if(e.shiftKey && document.activeElement===first){e.preventDefault(); last.focus();}
  else if(!e.shiftKey && document.activeElement===last){e.preventDefault(); first.focus();}
}

/* ---------- image lightbox ---------- */
var lastLbSrc=null;
function lbOpen(){return elLb.classList.contains('on');}
function openLightbox(src,alt){
  lastLbSrc=document.activeElement;
  var img=elLb.querySelector('img');
  img.src=src; img.alt=alt||'';
  elLb.setAttribute('aria-label',t('closeimg'));
  elLb.classList.add('on');
  try{elLb.querySelector('.tla-lb-close').focus();}catch(e){}
}
function closeLightbox(){
  if(!lbOpen())return;
  elLb.classList.remove('on');
  elLb.querySelector('img').src='';
  try{if(lastLbSrc)lastLbSrc.focus();}catch(e){}
  lastLbSrc=null;
}

/* ---------- mobile nav ---------- */
function navOpen(){return elNav.classList.contains('on');}
function focusBurger(){try{document.getElementById('tla-burger').focus();}catch(e){}}
function openNav(){
  elNav.classList.add('on');
  document.getElementById('tla-scrim').classList.add('on');
  document.getElementById('tla-burger').setAttribute('aria-expanded','true');
  // the drawer covers the page, so focus belongs in it — on the section you're reading
  var target=elNav.querySelector('.tla-nav-btn.active')||elNav.querySelector('.tla-nav-btn');
  if(target)try{target.focus();}catch(e){}
}
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
    /* Picking an edition re-renders the page, which destroys the button you just
       pressed: put focus back on its replacement and say what happened. */
    var vt=e.target.closest('[data-wnv]');
    if(vt){
      wnPick=vt.getAttribute('data-wnv'); renderWhatsNew();
      var again=elMain.querySelector('[data-wnv="'+CSS.escape(wnPick)+'"]');
      if(again){try{again.focus();}catch(err){}}
      var wn=data.whatsnew[wnPick];
      if(wn)announce('v'+wnPick+': '+wn['new'].length+' '+t('newentries')+', '+wn.updated.length+' '+t('updentries'));
      return;
    }
    var wc=e.target.closest('.tla-wncard'); if(wc){gotoTarget(wc.getAttribute('data-eid'),true); return;}
    var az=e.target.closest('.tla-azbtn'); if(az){setGlossFilter(az.getAttribute('data-az')); return;}
    var x=e.target.closest('.xref'); if(x){e.preventDefault(); gotoTarget(x.getAttribute('data-t'),true); return;}
    var a=e.target.closest('.anchor'); if(a){e.preventDefault(); gotoTarget(a.getAttribute('href').split('/')[1],true); return;}
    var mi=e.target.closest('.tla-montage-i'); if(mi){openFigInfo(mi); return;}
    var mimg=e.target.closest('.tla-montage-img'); if(mimg){openLightbox(mimg.src,mimg.alt); return;}
    var img=e.target.closest('.tla-fig img'); if(img){openLightbox(img.src,img.alt);}
  });
  elToc.addEventListener('click',function(e){var a=e.target.closest('[data-eid]'); if(a){e.preventDefault(); gotoTarget(a.getAttribute('data-eid'),true);}});
  elRes.addEventListener('click',function(e){var r=e.target.closest('.tla-res'); if(r){gotoTarget(r.getAttribute('data-eid'),true); closeSearch();}});
  elSOpen.addEventListener('click',openSearch);
  elSCancel.addEventListener('click',closeSearch);
  elSModal.addEventListener('click',function(e){if(e.target===elSModal)closeSearch();});
  elFigClose.addEventListener('click',closeFigInfo);
  elFigModal.addEventListener('click',function(e){if(e.target===elFigModal)closeFigInfo();});
  document.querySelector('.tla-lang').addEventListener('click',function(e){var b=e.target.closest('button'); if(b)setLang(b.getAttribute('data-l'));});
  elTheme.addEventListener('click',toggleTheme);
  document.getElementById('tla-home').addEventListener('click',function(e){e.preventDefault(); navigate(data.sections[0].id,false);});
  document.getElementById('tla-burger').addEventListener('click',function(){elNav.classList.contains('on')?closeNav():openNav();});
  document.getElementById('tla-scrim').addEventListener('click',closeNav);

  var qTimer=null;
  elQ.addEventListener('input',function(){clearTimeout(qTimer); qTimer=setTimeout(function(){search(elQ.value);},110);});
  elQ.addEventListener('focus',function(){if(elQ.value.trim().length>=2)search(elQ.value);});
  /* No Escape here: the document handler owns it, so that one press closes one
     layer. Handling it here too would close the dialog and then let the same
     press bubble on and dismiss whatever is underneath. */
  elQ.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){e.preventDefault();moveSel(1);}
    else if(e.key==='ArrowUp'){e.preventDefault();moveSel(-1);}
    else if(e.key==='Enter'){var items=elRes.querySelectorAll('.tla-res'); var chosen=items[resSel<0?0:resSel]; if(chosen){gotoTarget(chosen.getAttribute('data-eid'),true);closeSearch();}}
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Tab'){trapTab(e); return;}
    if(e.key==='Escape'){
      var d=openDialog();                                // innermost first; the drawer is one too
      if(d){e.preventDefault(); d.close();}
      return;
    }
    if(e.key==='/'&&!openDialog()&&!/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)){
      e.preventDefault(); openSearch();
    }
  });
  elMain.addEventListener('scroll',spy,{passive:true});
  window.addEventListener('hashchange',route);
  // the toolbar re-wraps as the pane narrows, changing how much it covers
  window.addEventListener('resize',syncStickyHeight,{passive:true});

  // clicking the backdrop (or the image) dismisses it, as before — but the
  // close button must not have its own click swallowed by the backdrop rule.
  elLb.addEventListener('click',closeLightbox);
}

/* ---------- boot ---------- */
function getJSON(url){
  return fetch(url).then(function(r){
    if(!r.ok)throw new Error(r.status+' '+r.statusText+' — '+url);
    return r.json();
  });
}
/* The error page can't use a fetched string: the fetch is what failed. */
function fatal(err){
  var msg=(PACKS[lang]&&pick(lang,'strings','loaderr'))||BOOT.loaderr;
  elMain.innerHTML='<div class="tla-doc"><div class="tla-note"><b>'+esc(msg)+'</b><br>'+esc(String(err&&err.message||err))+'</div></div>';
  try{console.error('The Living Arkham:',err);}catch(e){}
}

/* A language is fetched the first time it is shown, not up front, so the site
   costs the same to open whether it has two languages or twenty. */
var loading={}, uiTried={};

/* Fetch one language's interface strings. A fallback that is missing or fails to
   load must never break the page, so failure is recorded and shrugged off. */
function loadUI(c){
  if(PACKS[c])return Promise.resolve(true);
  if(uiTried[c])return Promise.resolve(false);
  uiTried[c]=true;
  var r=regOf(c);
  if(!r)return Promise.resolve(false);
  return getJSON(r.ui).then(function(u){PACKS[c]=u; return true;}, function(){return false;});
}
/* A fallback is only useful if its strings are actually here: fetch the whole
   chain (they are small) before rendering, or a key the pack hasn't translated
   would render as its own name. Each round marks what it tried, so this
   terminates even on a broken or circular chain. */
function loadChain(L){
  var need=chainOf(L).filter(function(c){return !PACKS[c] && !uiTried[c] && regOf(c);});
  if(!need.length)return Promise.resolve();
  return Promise.all(need.map(loadUI)).then(function(){return loadChain(L);});
}

function loadLang(L){
  // searchIndex is the last thing set, so it is what "fully loaded" means:
  // a load that died half-way must not be mistaken for a finished one.
  if(GRIM[L]&&PACKS[L]&&searchIndex[L])return Promise.resolve(L);
  if(loading[L])return loading[L];
  var reg=regOf(L);
  if(!reg)return Promise.reject(new Error('unknown language: '+L));
  uiTried[L]=true;
  loading[L]=Promise.all([
    GRIM[L]?Promise.resolve(GRIM[L]):getJSON(reg.data),
    PACKS[L]?Promise.resolve(PACKS[L]):getJSON(reg.ui)
  ]).then(function(res){
    GRIM[L]=res[0]; PACKS[L]=res[1];
    return loadChain(L);
  }).then(function(){
    // after the chain, so both may use strings that come from a fallback
    normalizeData(GRIM[L]);
    buildIndex(L);
    delete loading[L];
    return L;
  }, function(err){
    delete loading[L]; delete GRIM[L]; delete PACKS[L]; delete uiTried[L];
    throw err;
  });
  return loading[L];
}

/* Which language to open with: the URL wins, then the last one you chose, then
   what your browser asks for, then the site default. */
function initialLang(){
  var h=(location.hash||'').replace(/^#/,'').split('/')[0];
  if(known(h))return h;
  var saved=null; try{saved=localStorage.getItem('tla-lang');}catch(e){}
  if(known(saved))return saved;
  var navs=(navigator.languages||[navigator.language||'']).map(function(x){return String(x).toLowerCase();});
  for(var i=0;i<navs.length;i++){
    for(var j=0;j<LANGS.length;j++){
      var c=LANGS[j].code.toLowerCase();
      if(navs[i]===c||navs[i].split('-')[0]===c)return LANGS[j].code;
    }
  }
  return REG.default;
}

function boot(){
  var sg=document.querySelector('.tla-brand .tla-sigil'); SIGIL_SVG=sg?sg.outerHTML:'';
  getJSON('data/languages.json').then(function(reg){
    REG=reg; LANGS=reg.languages||[];
    if(!LANGS.length)throw new Error('data/languages.json lists no languages — run: python tools/ingest.py');
    lang=initialLang();
    return loadLang(lang);
  }).then(function(L){
    data=GRIM[L];
    applyLang(L);
    wireEvents();
    route();
  }).catch(fatal);
}
boot();
})();
