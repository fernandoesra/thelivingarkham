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
    elThemeMenu=document.getElementById('tla-thememenu'),
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
    var inner;
    if(r.kind==='link')          inner='<a class="xref" data-t="'+esc(r.target)+'">'+wrap(esc(r.t),r)+'</a>';
    else if(r.kind==='flowref')  inner='<a class="tla-flowref" data-flow="'+esc(r.target)+'">'+wrap(esc(r.t),r)+'</a>';
    else                         inner=wrap(esc(r.t),r);
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
/* ---------- phase diagrams ---------- */
/* The book draws each phase as a flowchart — boxes joined by arrows, teal for
   the numbered steps and red for the player windows. Rebuilt here rather than
   flattened to a list, because the shape IS the rule: it shows the loops.

   Semantically it is an ordered list, so a screen reader reads it as the
   sequence it is; the arrows are decoration and are hidden from it. */
/* The book heads the diagram and the prose that details it with the same words.
   On a page that shows both, that reads as the same thing twice — so the diagram
   says what it is. */
function diagBadge(e){
  return e.flow?' <span class="tla-diagbadge">'+esc(t('diagram'))+'</span>':'';
}
/* A callout is a notice the chapter raises in passing — the book sets it in a
   ruled box mid-page, not as a heading. Listing it as a subsection made "¡ALTO!"
   the first thing under "Juego y orden de resolución", as though the chapter
   opened with it. It stays exactly where the book puts it on the page; it just
   isn't one of the places you navigate to. */
function inToc(e){ return e.role!=='callout'; }
function flowStepNums(e){
  var out={}; (e.flow||[]).forEach(function(it){ if(it.n)out[it.n]=1; });
  return out;
}
/* "return to 2.2", "proceed to 2.2.2" — the book's loops are written as step
   numbers inside the boxes. Split those out into their own runs so the reader can
   click one and land on that box. Numbers read the same in every language, so no
   wording is involved.
   Splitting rather than rendering here keeps every other run property — a diff
   mark, bold, an icon — in the one place that knows about them: runsHTML. */
function flowRuns(runs,nums,base){
  var out=[];
  for(var i=0;i<runs.length;i++){
    var r=runs[i];
    if(r.kind!=='text'){out.push(r); continue;}
    var parts=r.t.split(/(\d+(?:\.\d+)+)/);
    for(var j=0;j<parts.length;j++){
      if(!parts[j])continue;
      var copy={},k;
      for(k in r){if(Object.prototype.hasOwnProperty.call(r,k))copy[k]=r[k];}
      copy.t=parts[j];
      if(j%2===1 && nums[parts[j]]){copy.kind='flowref'; copy.target=base+'-'+parts[j];}
      out.push(copy);
    }
  }
  return out;
}
function flowHTML(e){
  var nums=flowStepNums(e), base='fl-'+e.id;
  /* The loops run up the right-hand side, so the boxes give up room for them —
     the same amount on both sides, so the diagram stays centred on its boxes.
     Longest loop outermost, as the book nests them. */
  var loops=(e.loops||[]).slice().sort(function(a,b){return (b[0]-b[1])-(a[0]-a[1]);});
  /* longest first, and lane 0 is the outermost — so a long loop arcs around a
     short one instead of cutting through it, the way the book nests them */
  var lane={}; loops.forEach(function(l,i){lane[l[0]+'-'+l[1]]=i;});
  var pad=loops.length?(loops.length*12+8):0;
  var h='<div class="tla-flowwrap"><ol class="tla-flow" aria-label="'+esc(t('flowlabel'))+'"'
       +(pad?' style="padding-left:'+pad+'px;padding-right:'+pad+'px"':'')+'>';
  e.flow.forEach(function(it,idx){
    var b=e.blocks[it.i]; if(!b)return;
    var last=idx===e.flow.length-1;
    var id=it.n?(' id="'+esc(base+'-'+it.n)+'"'):'';
    h+='<li class="tla-flow-item is-'+esc(it.kind)+'">';
    h+='<div class="tla-flow-box"'+id+'>'+runsHTML(flowRuns(b.runs,nums,base))+'</div>';
    if(!last)h+='<span class="tla-flow-arrow" aria-hidden="true"></span>';
    h+='</li>';
  });
  h+='</ol>';
  /* Decoration: the loop is already stated in the box's own words ("return to
     2.2"), so a screen reader gains nothing from the drawing. */
  loops.forEach(function(l){
    /* left edge at the boxes' right edge, right edge out at this loop's lane —
       so the innermost loop's vertical line sits closest to the boxes, as in the
       book, and the longest one runs outermost. */
    var off=lane[l[0]+'-'+l[1]]*12;
    h+='<span class="tla-flow-loop" aria-hidden="true" data-from="'+l[0]+'" data-to="'+l[1]+'"'
      +' style="right:'+off+'px;width:'+(pad-off)+'px"></span>';
  });
  return h+'</div>';
}
/* The loops span from one box up to another, so their height is only knowable
   once the text has laid out — and it changes when the pane does. */
function layoutFlowLoops(){
  [].forEach.call(elMain.querySelectorAll('.tla-flowwrap'),function(wrap){
    var boxes=wrap.querySelectorAll('.tla-flow-box');
    [].forEach.call(wrap.querySelectorAll('.tla-flow-loop'),function(el){
      var a=boxes[+el.getAttribute('data-from')], b=boxes[+el.getAttribute('data-to')];
      if(!a||!b){el.style.display='none'; return;}
      var top=b.offsetTop+b.offsetHeight/2, bottom=a.offsetTop+a.offsetHeight/2;
      el.style.top=top+'px';
      el.style.height=Math.max(bottom-top,0)+'px';
    });
  });
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
/* The palettes live in css/app.css; this only names them and remembers the
   choice. The order here is the order in the picker. Keep it in step with the
   pre-paint script in index.html — that one runs before this file exists. */
var THEMES=['slate','moss','midnight','plum','neon','parchment'];
var OLDTHEMES={light:'parchment',dark:'slate'};   // what the two-theme toggle saved
function themeName(id){return pick(lang,'themes',id)||id;}
function currentTheme(){
  var t=document.documentElement.getAttribute('data-theme');
  if(OLDTHEMES[t])t=OLDTHEMES[t];
  return THEMES.indexOf(t)>=0?t:THEMES[0];
}
function applyThemeLabel(){
  if(elTheme)elTheme.setAttribute('aria-label',t('themetip')+': '+themeName(currentTheme()));
}
function setTheme(th){
  if(THEMES.indexOf(th)<0)th=THEMES[0];
  document.documentElement.setAttribute('data-theme',th);
  try{localStorage.setItem('tla-theme',th);}catch(e){}
  applyThemeLabel(); markTheme();
}
/* Swatches are painted BY the theme they offer — .tla-pal-<id> carries that
   theme's own tokens — so they can never drift from what they promise. The name
   beside each is the real label: six coloured circles tell a colour-blind reader
   nothing (WCAG 1.4.1), and are hidden from assistive tech for the same reason. */
function buildThemePicker(){
  var box=document.getElementById('tla-themeset'); if(!box)return;
  var lg=box.querySelector('legend');
  var h=lg?lg.outerHTML:'';
  THEMES.forEach(function(id){
    h+='<label class="tla-themeopt" data-t="'+esc(id)+'">'
      +'<input type="radio" name="tla-theme" value="'+esc(id)+'">'
      +'<span class="tla-swatch tla-pal-'+esc(id)+'" aria-hidden="true">'
      +'<i style="background:var(--gold)"></i><i style="background:var(--teal)"></i>'
      +'<i style="background:var(--ink)"></i></span>'
      +'<span class="tla-themeopt-n">'+esc(themeName(id))+'</span></label>';
  });
  box.innerHTML=h;
  markTheme();
}
function markTheme(){
  var cur=currentTheme();
  [].forEach.call(document.querySelectorAll('#tla-themeset input[name=tla-theme]'),function(r){
    r.checked=(r.value===cur);
  });
}
function themeMenuOpen(){return elThemeMenu&&!elThemeMenu.hidden;}
function openThemeMenu(){
  if(!elThemeMenu)return;
  buildThemePicker();
  elThemeMenu.hidden=false; elTheme.setAttribute('aria-expanded','true');
  var on=elThemeMenu.querySelector('input:checked')||elThemeMenu.querySelector('input');
  if(on)on.focus();
}
function closeThemeMenu(){
  if(!elThemeMenu)return;
  elThemeMenu.hidden=true; elTheme.setAttribute('aria-expanded','false');
}

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
/* A new edition of the Grimoire comes out in English and the translations follow
   months later. Until one lands, this language's own history is simply older —
   and saying nothing would look like nothing had happened, when in fact the news
   is exactly that there IS a new edition, just not in your language yet.
   The registry carries every language's newest edition, which is what makes that
   knowable before any of them is loaded. */
function cmpV(a,b){
  var x=String(a||'').split('.'), y=String(b||'').split('.');
  for(var i=0;i<Math.max(x.length,y.length);i++){
    var p=parseInt(x[i],10), q=parseInt(y[i],10);
    if(isNaN(p))p=0; if(isNaN(q))q=0;
    if(p!==q)return p<q?-1:1;
  }
  return 0;
}
function myVer(code){
  for(var i=0;i<LANGS.length;i++){if(LANGS[i].code===code)return LANGS[i].v||null;}
  return null;
}
/* Languages whose newest edition is newer than this one's, newest first. No
   language is "the source": whoever is ahead is ahead. */
function langsAhead(code){
  var me=myVer(code); if(!me)return [];
  return LANGS.filter(function(L){return L.code!==code && L.v && cmpV(L.v,me)>0;})
              .sort(function(a,b){return cmpV(b.v,a.v);});
}
function normalizeData(g){
  var li=latestInfo(g);
  /* The chapter also exists when this language has no news of its own but another
     language does — that IS the news. */
  if((li||langsAhead(g.lang).length) && !g.sections.some(function(x){return x.id==='novedades';})){
    g.sections.splice(1,0,{num:'',key:'whatsnew',id:'novedades',kind:'whatsnew',
      title:pick(g.lang,'strings','news')||'What\'s New',ver:li,intro:[],entries:[],figures:[]});
  }
}
/* the nav badge counts what the newest edition brought */
function wnCount(s){var wn=s.ver&&data.whatsnew&&data.whatsnew[s.ver.v]; return wn?(wn['new'].length+wn.updated.length):0;}

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
    var wc=news?wnCount(s):0;
    var cnt=news?(wc?('<span class="tla-nav-cnt new">'+wc+'</span>'):''):(n?('<span class="tla-nav-cnt">'+n+'</span>'):'');
    h+='<div class="tla-nav-sec'+(news?' is-news':'')+'" data-si="'+si+'" id="navsec-'+s.id+'">';
    h+='<button class="tla-nav-btn" type="button" data-si="'+si+'">'+num+'<span>'+esc(s.title)+'</span>'+cnt+'</button>';
    if(s.kind!=='glossary' && n){
      var subs=sectionEntries(s).filter(inToc);
      if(subs.length){
        h+='<div class="tla-sublist">';
        subs.forEach(function(e){h+='<button class="tla-sublink" type="button" data-eid="'+esc(e.id)+'">'+titleHTML(e)+diagBadge(e)+'</button>';});
        h+='</div>';
      }
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
/* The A-Z bar is pinned, so whatever it takes it takes forever. On a 375px phone
   its 27 letters wrap to five rows — 203px of a 667px screen, a third of the
   device, permanently. So it folds.
   `azOpen` is the reader's own answer and starts as null, meaning "not asked":
   until they touch it, the bar follows the screen (open on a desktop, folded on a
   phone), and once they do, their answer sticks through re-renders and resizes.
   That is why it is a tri-state and not a boolean. */
var azOpen=null;
var AZ_AUTO='(max-width:820px)';                  // the width the nav folds at too
function azFolds(){return window.matchMedia&&window.matchMedia(AZ_AUTO).matches;}
function azIsOpen(){return azOpen===null?!azFolds():azOpen;}
function azSummary(s){
  var total=sectionEntries(s).length, shown=visibleEntries(s).length;
  /* Folded, this line is the only thing saying a filter is on at all — so it
     names the letter, not just the tally. */
  return glossFilter==='all' ? (total+' '+t('entries'))
       : (glossFilter+' · '+shown+' '+t('of')+' '+total+' '+t('entries'));
}
function azFilterBar(s){
  var present={}; sectionEntries(s).forEach(function(e){present[entryLetter(e)]=1;});
  var order=azOrder(present);
  var open=azIsOpen();
  var h='<div class="tla-azfilter'+(open?'':' is-folded')+'">';
  h+='<button class="tla-aztoggle" type="button" id="tla-aztoggle" aria-expanded="'+open+'" aria-controls="tla-azpanel">';
  h+='<span class="tla-azlabel">'+esc(t('filterby'))+'</span>';
  h+='<span class="tla-azcount">'+esc(azSummary(s))+'</span>';
  h+='<svg class="tla-azchev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
  h+='</button>';
  h+='<div class="tla-azpanel" id="tla-azpanel"'+(open?'':' hidden')+'><div class="tla-azrow">';
  h+='<button class="tla-azbtn all'+(glossFilter==='all'?' active':'')+'" type="button" data-az="all" aria-pressed="'+(glossFilter==='all')+'">'+t('all')+'</button>';
  order.forEach(function(c){ h+='<button class="tla-azbtn'+(glossFilter===c?' active':'')+'" type="button" data-az="'+esc(c)+'" aria-pressed="'+(glossFilter===c)+'">'+esc(c)+'</button>'; });
  h+='</div></div></div>';
  return h;
}
/* The footer's credits. Unlike the A-Z bar there is no tri-state: above the
   breakpoint there is room, so they are simply always there and the button does
   not exist. JS owns the `hidden` attribute rather than CSS hiding the panel,
   because `hidden` is what takes it out of the accessibility tree and the tab
   order — and it must never be set on a wide screen, where the credits ARE on
   the page and saying otherwise would be a lie to a screen reader. */
var FOOT_FOLDS='(max-width:820px)';
var footOpen=false;
function footFolds(){return !!(window.matchMedia&&window.matchMedia(FOOT_FOLDS).matches);}
function syncFoot(){
  var b=document.getElementById('tla-foot-body'), btn=document.getElementById('tla-foot-toggle');
  if(!b||!btn)return;
  var folded=footFolds()&&!footOpen;
  b.hidden=folded;
  btn.setAttribute('aria-expanded',String(!folded));
}
function toggleFoot(){footOpen=!footOpen; syncFoot();}
function toggleAz(){
  azOpen=!azIsOpen();
  var bar=elMain.querySelector('.tla-azfilter'); if(!bar)return;
  var btn=bar.querySelector('.tla-aztoggle'), panel=bar.querySelector('.tla-azpanel');
  bar.classList.toggle('is-folded',!azOpen);
  btn.setAttribute('aria-expanded',String(azOpen));
  panel.hidden=!azOpen;
  syncStickyHeight();          // the pinned bar just changed height
}
function setGlossFilter(v){
  glossFilter=v; render(curSec.id,null,false); elMain.scrollTop=0;
  var n=visibleEntries(curSec).length;
  announce((v==='all'?t('all'):v)+': '+n+' '+t('entries'));
}

/* ---------- render section ---------- */
/* ---------- card anatomy ---------- */
/* The book draws this chapter: a card, numbered diamonds around it, an arrow
   from each diamond to the exact spot it means, and a key explaining the
   numbers. Shipped as a page scan — which is what it used to be — none of that
   text can be selected, searched, translated or read aloud, and the arrows say
   nothing to anyone who cannot see them.

   So only the card stays a picture. Each arrow becomes a marker sitting where
   its arrowhead pointed (tools/card_anatomy.py reads that out of the PDF's own
   vector art), and the key becomes a real ordered list, auto-linked into the
   glossary like any other prose.

   The link between the two runs both ways: a marker names its key item, and a
   key item highlights every marker that points at it. That is one `data-hot`
   attribute plus CSS — no per-node state to keep in sync. */
function anatTerm(it){ return plainOfRuns(it.term)||String(it.n); }
function anatMarkers(card,k,items){
  var h='';
  card.markers.forEach(function(m,i){
    var it=items[m.n]; if(!it)return;
    var lbl=t('anatmark').replace('{n}',m.n).replace('{t}',anatTerm(it));
    h+='<button class="tla-anatmark" type="button" data-n="'+esc(String(m.n))+'"'
      +' data-key="'+esc(k.id)+'" aria-label="'+esc(lbl)+'"'
      +' style="left:'+m.x+'%;top:'+m.y+'%">'+esc(String(m.n))+'</button>';
  });
  return h;
}
/* One card at a time. The key explains eighteen things spread over eight cards,
   so showing all eighteen beside all eight meant the card and the words that
   describe it were never on screen together — you cannot look from one to the
   other if you have to scroll between them.

   So the cards become tabs, and the panel shows one card next to just the items
   that card actually carries: four to six lines, no scrolling, the card right
   there. Which items those are is exactly what the book's arrows said, which is
   why they were worth reading out of the PDF in the first place. Every item
   belongs to some card, so walking the tabs still reads the whole key. */
function anatKeyItems(k,c){
  var want={}; c.markers.forEach(function(m){want[m.n]=1;});
  return k.items.filter(function(it){return want[it.n];});
}
function anatItemHTML(kid,it){
  var h='<li id="'+kid+'-'+esc(String(it.n))+'" data-n="'+esc(String(it.n))+'">';
  h+='<span class="tla-anat-n" aria-hidden="true">'+esc(String(it.n))+'</span>';
  /* The book bolds the term and ends it with a colon. If an edition ever prints
     an item with no term at all, don't emit an empty <b> and a stray colon. */
  h+='<span class="tla-anat-txt">';
  h+=it.term.length?('<b class="tla-anat-term">'+runsHTML(it.term)+'</b>'
                     +(it.desc.length?': ':'')):'';
  h+=runsHTML(it.desc)+'</span></li>';
  return h;
}
function anatomyHTML(s){
  var h='';
  (s.keys||[]).forEach(function(k,ki){
    var items={}; k.items.forEach(function(it){items[it.n]=it;});
    var kid='anat-'+esc(k.id);
    /* Open on a card the book actually annotates. The player key's first card is
       the investigator mini-card, which carries no callouts at all — landing on
       it showed an empty panel and made the whole chapter look broken. */
    var sel=0;
    for(var ci=0;ci<k.cards.length;ci++){ if(k.cards[ci].markers.length){sel=ci; break;} }
    h+='<section class="tla-anat" data-key="'+esc(k.id)+'" aria-labelledby="'+kid+'-h">';
    h+='<h2 class="tla-anat-h" id="'+kid+'-h">'+esc(k.title)+'</h2>';
    h+='<p class="tla-anat-hint" id="'+kid+'-hint">'+esc(t('anathint'))+'</p>';
    /* A tablist: one tab per card. Roving tabindex + arrow keys, so the whole
       chapter costs one Tab stop to reach and arrows to walk. */
    h+='<div class="tla-anat-tabs" role="tablist" aria-labelledby="'+kid+'-h">';
    k.cards.forEach(function(c,i){
      h+='<button class="tla-anat-tab" role="tab" type="button" id="'+kid+'-tab-'+esc(c.id)+'"'
        +' aria-controls="'+kid+'-panel-'+esc(c.id)+'" aria-selected="'+(i===sel?'true':'false')+'"'
        +' tabindex="'+(i===sel?'0':'-1')+'">'+esc(c.title)+'</button>';
    });
    h+='</div>';
    k.cards.forEach(function(c,i){
      var sub=anatKeyItems(k,c);
      var wh=c.w?(' width="'+c.w+'" height="'+c.h+'"'):'';
      h+='<div class="tla-anat-panel" role="tabpanel" id="'+kid+'-panel-'+esc(c.id)+'"'
        +' aria-labelledby="'+kid+'-tab-'+esc(c.id)+'"'+(i===sel?'':' hidden')+'>';
      h+='<div class="tla-anat-split">';
      h+='<figure class="tla-anatcard" id="anatcard-'+esc(c.id)+'">';
      h+='<div class="tla-anatcard-frame">';
      h+='<img class="tla-anatcard-img" loading="lazy" src="assets/img/'+esc(c.file)+'"'+wh
        +' alt="'+esc(t('anatalt').replace('{t}',c.title))+'">';
      h+=anatMarkers(c,k,items);
      h+='</div>';
      h+='<figcaption class="tla-anatcard-t">'+esc(c.title)+'</figcaption>';
      h+='</figure>';
      if(sub.length){
        /* list-style:none strips list semantics in Safari; role=list puts them back. */
        h+='<ol class="tla-anat-key" role="list">';
        sub.forEach(function(it){h+=anatItemHTML(kid,it);});
        h+='</ol>';
      }else{
        h+='<p class="tla-anat-none">'+esc(t('anatnone'))+'</p>';
      }
      h+='</div></div>';
    });
    h+='</section>';
  });
  return h;
}
/* Standard tablist keys: arrows walk, Home/End jump, and the tab that is
   selected is the only one in the Tab order. */
function anatSelect(tab){
  var sec=tab.closest('.tla-anat'); if(!sec)return;
  anatHot(sec,null);
  [].forEach.call(sec.querySelectorAll('.tla-anat-tab'),function(b){
    var on=b===tab;
    b.setAttribute('aria-selected',on?'true':'false');
    b.tabIndex=on?0:-1;
    var p=document.getElementById(b.getAttribute('aria-controls'));
    if(p)p.hidden=!on;
  });
}
function anatTabKeys(e){
  var tab=e.target.closest('.tla-anat-tab'); if(!tab)return;
  var tabs=[].slice.call(tab.closest('.tla-anat-tabs').querySelectorAll('.tla-anat-tab'));
  var i=tabs.indexOf(tab), n=tabs.length, j=-1;
  if(e.key==='ArrowRight'||e.key==='ArrowDown')j=(i+1)%n;
  else if(e.key==='ArrowLeft'||e.key==='ArrowUp')j=(i-1+n)%n;
  else if(e.key==='Home')j=0;
  else if(e.key==='End')j=n-1;
  if(j<0)return;
  e.preventDefault(); anatSelect(tabs[j]); tabs[j].focus();
}
/* Hovering or focusing either side lights the other. One function owns the
   whole highlight: it clears everything, then lights what matches. There is no
   per-element state to leak, so a pointer that leaves mid-animation, a focus
   that jumps across cards, and a re-render all land in the same place.
   `data-hot` on the section dims the rest; `.is-hot` marks the chosen ones. */
function anatHot(el,n){
  var sec=el&&el.closest?el.closest('.tla-anat'):null; if(!sec)return;
  [].forEach.call(sec.querySelectorAll('.is-hot'),function(x){x.classList.remove('is-hot');});
  if(n==null){sec.removeAttribute('data-hot'); return;}
  sec.setAttribute('data-hot',n);
  [].forEach.call(sec.querySelectorAll('[data-n="'+cssEsc(n)+'"]'),function(x){x.classList.add('is-hot');});
}
function bindAnatomy(){
  [].forEach.call(elMain.querySelectorAll('.tla-anat'),function(sec){
    function hot(e){
      var m=e.target.closest('.tla-anatmark,.tla-anat-key > li');
      /* Leaving a marker for the image is still "inside"; only a null target clears. */
      if(m)anatHot(m,m.getAttribute('data-n'));
      else if(e.type==='mouseleave'||e.type==='focusout')anatHot(sec,null);
    }
    sec.addEventListener('mouseover',hot);
    sec.addEventListener('mouseleave',function(){anatHot(sec,null);});
    sec.addEventListener('focusin',hot);
    sec.addEventListener('focusout',function(e){
      if(!sec.contains(e.relatedTarget))anatHot(sec,null);
    });
    sec.addEventListener('click',function(e){
      var tab=e.target.closest('.tla-anat-tab');
      if(tab){anatSelect(tab); return;}
      var b=e.target.closest('.tla-anatmark'); if(!b)return;
      /* the item is in the open panel, so scope the lookup to it */
      var panel=b.closest('.tla-anat-panel')||sec;
      var li=panel.querySelector('[data-n="'+cssEsc(b.getAttribute('data-n'))+'"].tla-anat-key>li, '
             +'.tla-anat-key > li[data-n="'+cssEsc(b.getAttribute('data-n'))+'"]');
      if(!li)return;
      anatHot(b,b.getAttribute('data-n'));
      keepInView(li,elMain);
      li.classList.remove('flash'); void li.offsetWidth; li.classList.add('flash');
    });
    sec.addEventListener('keydown',anatTabKeys);
  });
}
/* getElementById would be simpler, but these ids carry pack-authored slugs;
   querySelector needs them escaped. CSS.escape isn't in older Safari. */
function cssEsc(s){
  return (window.CSS&&CSS.escape)?CSS.escape(s):String(s).replace(/[^\w-]/g,'\\$&');
}

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
  if(s.kind==='anatomy'){h+=anatomyHTML(s);}
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
    /* role comes from how the book prints the heading: a STOP! callout, the
       opening of a subsection, or nothing special. */
    var role=e.role?(' is-'+e.role):'';
    /* h2: an entry sits directly under the chapter's h1. Jumping straight to h3
       would leave a hole in the outline a screen reader navigates by. */
    h+='<article class="tla-entry'+role+(brandNew?' is-new':'')+(lv&&isChangedIn(e,lv)?' is-upd':'')+'" id="e-'+esc(e.id)+'">';
    h+='<h2>'+titleHTML(e)+diagBadge(e)+verBadge(e)+'<a class="anchor" href="#'+lang+'/'+esc(e.id)+'" title="'+esc(t('jump'))+'" aria-label="'+esc(t('jump'))+'">§</a></h2>';
    h+=e.flow?flowHTML(e):blocksHTML(e.blocks,brandNew);
    h+=verProvenance(e);
    h+=figuresHTML(e,esc(e.id));
    h+='</article>';
  });
  h+='</div>';
  elMain.innerHTML=h;
  syncStickyHeight();          // before any scroll-to, so the target clears the toolbar
  layoutFlowLoops();
  bindAnatomy();
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
/* "There is a newer edition, but not in your language yet." Named languages, a
   real date, and a way straight into the edition that does exist — a notice the
   reader can act on rather than just be told. */
function pendingHTML(){
  var ahead=langsAhead(lang); if(!ahead.length)return '';
  var top=ahead[0];
  var names=ahead.map(function(L){return L.name;}).join(', ');
  var h='<section class="tla-pending">';
  h+='<i class="tla-eldersign tla-pending-star" aria-hidden="true"></i>';
  h+='<div class="tla-pending-body">';
  h+='<h2 class="tla-pending-t">'+esc(t('pendingt').replace('{v}',top.v).replace('{l}',names))+'</h2>';
  h+='<p class="tla-pending-d">'+esc(t('pendingd').replace('{v}',top.v)
      .replace('{d}',fmtDate(top.date)).replace('{l}',names))+'</p>';
  /* Switching language is what this button does, so it says so: the reader is
     about to leave their own language, and that should not be a surprise. */
  h+='<button class="tla-pending-cta" type="button" data-golang="'+esc(top.code)+'" lang="'+esc(top.code)+'">'
    +esc(t('pendingcta').replace('{l}',top.name))+' →</button>';
  h+='</div></section>';
  return h;
}
function renderWhatsNew(){
  var vs=wnVersions();
  var pending=pendingHTML();
  if(!vs.length && !pending){elMain.innerHTML=''; elToc.innerHTML=''; return;}
  var cur=null;
  for(var i=0;i<vs.length;i++){if(vs[i].v===wnPick)cur=vs[i];}
  if(!cur)cur=vs[0];
  var wn=cur?data.whatsnew[cur.v]:null;

  var h='<div class="tla-doc">';
  h+='<div class="tla-crumb">The Living Arkham</div>';
  h+='<h1 class="tla-h1">'+esc(t('news'))+'</h1><div class="tla-rule"></div>';
  h+=pending;

  // the whole history, always — one chip per edition, newest first. It still
  // matters when there is no news: it says which edition you are actually on.
  h+='<div class="tla-vertabs" role="group" aria-label="'+esc(t('history'))+'">';
  vs.forEach(function(v){
    var n=data.whatsnew[v.v], count=n['new'].length+n.updated.length;
    h+='<button class="tla-vertab'+(cur&&v.v===cur.v?' active':'')+'" type="button" data-wnv="'+esc(v.v)+'"'
      +' aria-pressed="'+(!!cur&&v.v===cur.v)+'">'
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

  if(cur){
    h+='<div class="tla-note">'+esc(t('newsintro'))+'</div>';
    if(wn['new'].length){h+='<h2 class="tla-wnh"><span class="tla-vbadge new">'+esc(t('newbadge'))+'</span> '+esc(t('newentries'))+' <span class="tla-wncount">'+wn['new'].length+'</span></h2>'
      +'<p class="tla-wnhelp">'+esc(t('newhelp').replace('{v}',cur.v))+'</p>'+wnList(wn['new'],'new');}
    if(wn.updated.length){h+='<h2 class="tla-wnh"><span class="tla-vbadge upd">'+esc(t('updbadge'))+'</span> '+esc(t('updentries'))+' <span class="tla-wncount">'+wn.updated.length+'</span></h2>'
      +'<p class="tla-wnhelp">'+esc(t('updhelp').replace('{v}',cur.v))+'</p>'+wnList(wn.updated,'upd');}
  }
  h+='</div>';
  elMain.innerHTML=h; elToc.innerHTML=''; elMain.scrollTop=0;
}
function wnList(items,cls){
  var h='<div class="tla-wngrid">';
  items.forEach(function(it){
    // a whole chapter can change too — the FAQ gains answers in its own lead text
    var where=it.chapter?esc(t('chapter')):((it.num?esc(it.num)+' · ':'')+esc(it.sec));
    /* The card already says "rewritten", so the title's own diff marks would only
       repeat it — same reason titleHTML suppresses them. */
    h+='<button class="tla-wncard '+cls+(it.chapter?' is-chapter':'')+'" type="button" data-eid="'+esc(it.id)+'">'
      +'<span class="tla-wntitle">'+(it.titleRuns?runsHTML(it.titleRuns,true):esc(it.title))+'</span>'
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
/* Which chapters are worth pointing at, by the pack's shared section keys and
   never by their titles — the same chapter is "Glosario" in one language and
   "Glossary of Terms and Keywords" in the next, and a German pack will name it a
   third thing. The keys are the fixed vocabulary every pack already agrees on
   (langpack.SECTION_KEYS), so this needs no translation and no pack changes. */
var FLAGS=[
  {id:'relevant',    keys:['whatsnew','glossary']},
  {id:'recommended', keys:['timing','skill-tests','errata']}
];
function flagOf(s2){
  for(var i=0;i<FLAGS.length;i++){ if(FLAGS[i].keys.indexOf(s2.key)>=0)return FLAGS[i].id; }
  return null;
}
/* The two flags, explained once above the grid, so the ribbons below mean
   something the first time they are seen. */
function flagKeyHTML(){
  var live={}; data.sections.forEach(function(s2){var f=flagOf(s2); if(f)live[f]=1;});
  var shown=FLAGS.filter(function(f){return live[f.id];});
  if(!shown.length)return '';
  var h='<ul class="tla-pennantkey">';
  shown.forEach(function(f){
    h+='<li class="tla-pennantkey-i"><span class="tla-pennant is-'+f.id+'">'+esc(t('flag'+f.id))+'</span>'
      +'<span class="tla-pennant-d">'+esc(t('flag'+f.id+'d'))+'</span></li>';
  });
  return h+'</ul>';
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
  h+=flagKeyHTML();
  h+='<div class="tla-cards">';
  data.sections.forEach(function(s2,si){
    if(s2.kind==='intro')return;
    var news=s2.kind==='whatsnew';
    var n=sectionEntries(s2).length;
    var num=news?'<i class="tla-eldersign" aria-hidden="true"></i>':esc(s2.num||'•');
    var meta;
    if(!news)meta=n+' '+t('entries');
    else if(s2.ver)meta=t('newver')+' · v'+s2.ver.v;
    else{var ah=langsAhead(lang)[0];
      meta=ah?t('pendingcard').replace('{v}',ah.v).replace('{l}',ah.name):t('news');}
    var fl=flagOf(s2);
    h+='<button class="tla-card'+(news?' news':'')+(fl?' has-pennant':'')+'" type="button" data-si="'+si+'">';
    /* The ribbon is text, not decoration: it is the whole point of the flag, so a
       screen reader gets it as part of the card's name rather than a coloured
       shape it cannot see. */
    if(fl)h+='<span class="tla-pennant tla-cardpennant is-'+fl+'">'+esc(t('flag'+fl))+'</span>';
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
  var list=ents.filter(inToc);
  if(!list.length){elToc.innerHTML=''; return;}
  var h='<h2 class="tla-toc-h">'+esc(t('onthispage'))+'</h2>';
  /* A subsection opens the entries that follow it, so it heads them rather than
     hanging under them — it used to be the indented one, which was backwards. */
  list.forEach(function(e){
    h+='<a href="#'+lang+'/'+esc(e.id)+'" data-eid="'+esc(e.id)+'"'
      +(e.role==='subhead'?' class="is-subhead"':'')+'>'+titleHTML(e)+diagBadge(e)+'</a>';
  });
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
    /* modal:false — Escape must close it, but Tab must be able to LEAVE it: it is
       a disclosure hanging off a header button, not a modal. Trapping Tab in a
       six-item colour menu would strand the keyboard on it. */
    {box:elThemeMenu,isOpen:themeMenuOpen,modal:false,
     close:function(){closeThemeMenu(); elTheme.focus();}},
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
  var d=openDialog(); if(!d||d.modal===false)return;
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
    var gl=e.target.closest('[data-golang]');
    if(gl){setLang(gl.getAttribute('data-golang')); return;}
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
    if(e.target.closest('.tla-aztoggle')){toggleAz(); return;}
    var az=e.target.closest('.tla-azbtn'); if(az){setGlossFilter(az.getAttribute('data-az')); return;}
    /* a step number inside a diagram: jump to that box and flash it, so the
       loops the book draws with arrows can actually be followed */
    var fr=e.target.closest('.tla-flowref');
    if(fr){
      var box=document.getElementById(fr.getAttribute('data-flow'));
      if(box){
        box.scrollIntoView({block:'center'});
        box.classList.remove('flash'); void box.offsetWidth; box.classList.add('flash');
      }
      return;
    }
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
  elTheme.addEventListener('click',function(){themeMenuOpen()?closeThemeMenu():openThemeMenu();});
  /* Radios fire change on arrow-key moves too, so this IS the live preview. */
  elThemeMenu.addEventListener('change',function(e){
    var r=e.target.closest('input[name=tla-theme]'); if(r)setTheme(r.value);
  });
  /* Enter/Space on a radio commits and closes; the choice is already applied. */
  elThemeMenu.addEventListener('keydown',function(e){
    if(e.key==='Enter'){e.preventDefault(); closeThemeMenu(); elTheme.focus();}
  });
  /* clicking away closes it — a menu, not a modal: it traps nothing */
  document.addEventListener('mousedown',function(e){
    if(themeMenuOpen() && !elThemeMenu.contains(e.target) && !elTheme.contains(e.target))closeThemeMenu();
  });
  /* and tabbing away closes it too, so it never lingers behind the reader */
  elThemeMenu.addEventListener('focusout',function(e){
    if(!themeMenuOpen())return;
    var to=e.relatedTarget;
    if(to && (elThemeMenu.contains(to)||elTheme.contains(to)))return;
    if(to)closeThemeMenu();          // focus went elsewhere on purpose
  });
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
  document.getElementById('tla-foot-toggle').addEventListener('click',toggleFoot);
  syncFoot();
  var azWas=azIsOpen();
  window.addEventListener('resize',function(){
    /* Crossing the fold width changes what "auto" means, so the bar has to be
       rebuilt — but only if the reader has not overridden it, and only when the
       answer really flipped: this fires on every pixel of a drag. */
    if(azOpen===null && azIsOpen()!==azWas && curSec && curSec.kind==='glossary'){
      azWas=azIsOpen(); render(curSec.id);
    }
    syncFoot();                       // the breakpoint decides whether it folds at all
    syncStickyHeight(); layoutFlowLoops();
  },{passive:true});

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
