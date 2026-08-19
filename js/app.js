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
    FAQ = {},         // code -> FAQ chapter 1 corpus (loaded on demand, may be absent)
    TABOO = {},       // code -> interactive taboo list (loaded on demand, may be absent)
    TABOOCARDS = {},  // code -> {cards, beta}: the taboo card reprints (own, or English fallback)
    PACKS = {},       // code -> ui.json
    REG = null,       // the language registry
    LANGS = [];       // registry entries, in display order
var BLOG='https://rinconmiskatonic.org/', SIGIL_SVG='';
/* Who drew the banner. A credit, not content: the same fact in every language, so it lives
   here rather than in each pack's strings — only the word "Illus." is translated. */
var HERO_ART={by:'Aurore Folny', url:'https://www.artstation.com/aurorefolny'};

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
/* A counted noun. "1 entradas" was on the page because the app just concatenated a
   number and one fixed word — English and Spanish both need two forms, and Polish
   needs three, Arabic six. So the pack gives the forms and the browser picks:

     "entries": {"one": "entrada", "other": "entradas"}

   The categories are CLDR's, chosen for the pack's own locale, so a pack only ever
   writes the forms its language actually has and no plural rule is hardcoded here. A
   pack that gives a plain string keeps it for every count — a language with one form
   is then correct by saying so, not by accident. */
function plural(key,n){
  var v=pick(lang,'strings',key);
  if(v==null)return key;
  if(typeof v==='string')return v;
  var cat='other';
  /* the pack's declared locale, not its code: 'pt-BR' is a locale, 'ptbr' is not,
     and a bad tag throws rather than guessing */
  try{cat=new Intl.PluralRules(uiOf(lang,'locale',lang)).select(n);}catch(e){}
  return v[cat]!=null?v[cat]:(v.other!=null?v.other:key);
}
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
/* The name of a language as *this* language says it. One field, two different
   needs: the switcher must show each language its OWN name — you find your language
   by looking for the word you know — while prose must use the reader's word for it
   ("se publicó en inglés", not "en English"). The registry only carries the endonym,
   so the exonym comes from the browser's CLDR tables: a new pack is then named
   correctly in every other language without anyone maintaining an N×N matrix of
   names, which is the only version of this that keeps adding a language data-only.

   Used verbatim: CLDR already cases each name the way its own language cases it
   (es "inglés", en "English", de "Englisch"), so imposing a case would break two
   languages to suit a third. {l} must therefore never open a sentence.

   The pack is read directly, never through pick(): pick() walks the fallback chain,
   which ends at English, and an English answer is precisely the bug here. */
function langName(code){
  var pack=PACKS[lang]||{};
  var own=(regOf(code)||{}).name||code;             // the endonym: always present
  if(pack.langNames&&pack.langNames[code])return pack.langNames[code];
  if(typeof Intl==='undefined'||!Intl.DisplayNames)return own;   // pre-2021 browser
  var loc=pack.locale||lang;
  try{
    /* An unsupported locale does NOT throw — it silently resolves to the RUNTIME's
       default locale, so a pack whose locale CLDR doesn't know would be named by
       whatever OS the reader happens to be on. That reads as correct on the author's
       own machine and wrong on everyone else's, which is why it is checked rather
       than caught. */
    if(!Intl.DisplayNames.supportedLocalesOf([loc]).length)return own;
    /* fallback:'none' -> undefined for an unknown code, rather than handing back the
       code itself dressed up as a name. */
    return new Intl.DisplayNames([loc],{type:'language',fallback:'none'}).of(code)||own;
  }catch(e){ return own; }                          // a structurally invalid code throws
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
    elSClear=document.getElementById('tla-search-clear'),
    elFigModal=document.getElementById('tla-figmodal'),
    elFigHead=document.getElementById('tla-figmodal-h'),
    elFigBody=document.getElementById('tla-figmodal-body'),
    elFigClose=document.getElementById('tla-figmodal-close'),
    elLb=document.getElementById('tla-lb'),
    elDonate=document.getElementById('tla-donate'),
    elDiscord=document.getElementById('tla-discord'),
    elGh=document.getElementById('tla-gh'),
    elUbDraw=document.getElementById('tla-ubdraw');
var lastFigBtn=null;
/* set by boot() from the registry — never hardcoded to any language */
var lang='', data=null, curSec=null, searchIndex={}, resSel=-1, glossFilter='all', firstRoute=true;

/* ---------- helpers ---------- */
function esc(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
/* A click the browser should keep: middle/right button, or any modifier — i.e. the
   reader asking for a new tab or window, not for us to route them. */
function modClick(e){return e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey;}
function announce(msg){if(elLive){elLive.textContent=''; setTimeout(function(){elLive.textContent=msg;},40);}}
/* Labels come from a pack, so they are escaped like any other authored text:
   a label containing a quote would otherwise break out of the attribute. */
function iconHTML(name){return '<i class="ico ico-'+esc(name)+'" title="'+esc(iconLabel(name))+'"></i>';}
/* A set/campaign/scenario icon recovered from the books' vector art (tools/faq_seticons.py and
   tools/grim_vecicons.py). Not a font glyph, so it is not in icons.css: its mask is the
   per-shape SVG, named by the shape's fingerprint. The build works out which campaign most of
   these marks stand for (tools/adb_resolve.py) and stores it as `pn`, so the icon can say
   "Legado de Dunwich" instead of the generic label; one that was never identified keeps it. */
function seticonHTML(r){var u='assets/faqsets/'+esc(r.fp)+'.svg', lbl=r.pn||t('faqseticon');
  return '<i class="ico tla-seticon" role="img" aria-label="'+esc(lbl)+'" title="'+esc(lbl)
    +'" style="-webkit-mask-image:url('+u+');mask-image:url('+u+')"></i>';}
/* flat: render every interactive run (link, card link, flow ref) as plain text. A title
   goes inside a nav <button> and a table-of-contents <a>, and an interactive element
   nested in either is invalid HTML and a "nested-interactive" a11y failure — the outer
   control already navigates, so the inner link is redundant there anyway. */
function runsHTML(runs,suppressNew,flat){
  var h='';
  for(var i=0;i<runs.length;i++){var r=runs[i];
    if(r.kind==='icon'){h+=iconHTML(r.name); continue;}
    if(r.kind==='seticon'){if(!flat)h+=seticonHTML(r); continue;}
    if(r.kind==='pageref'){h+='<span class="tla-pageref" title="'+esc(t('origpage')+' '+r.n)+'">('+esc(t('origpage'))+' '+esc(r.n)+')</span>'; continue;}
    var inner;
    if(flat && (r.kind==='link'||r.kind==='adbcard'||r.kind==='flowref')){h+=wrap(esc(r.t),r); continue;}
    /* A real href, not a bare <a>. Without one an anchor is not focusable, is not in
       the tab order, and the accessibility tree drops it entirely (role "none",
       ignored) — so every cross-reference in the book was mouse-only and silent to a
       screen reader. The href is also what makes Back work and what lets a reader
       middle-click a term into a new tab. The delegated handler intercepts a plain
       left click to add the flash; anything else is left to the browser. */
    if(r.kind==='link')          inner='<a class="xref" href="#'+esc(lang)+'/'+esc(r.target)+'" data-t="'+esc(r.target)+'">'+wrap(esc(r.t),r)+'</a>';
    /* A card named in the errata/FAQ. The build resolves most references to the exact card
       (name + collection number + the product's icon — tools/adb_resolve.py), and those link
       straight to it, naming the product in the tooltip so the reader knows which printing
       they are opening. Anything it could not pin down keeps the honest fallback: a search,
       which lists every printing. External either way, so it opens in a new tab. */
    else if(r.kind==='adbcard'){
      var tip=t('viewadb')+(r.pn?' · '+r.pn:'');
      inner='<a class="tla-adbcard" href="'+esc(r.code?adbCardUrl(r.code):adbSearchUrl(r.q))+'" target="_blank" rel="noopener" title="'+esc(tip)+'">'+wrap(esc(r.t),r)+'</a>';
    }
    /* A button, not a link: this scrolls to a box inside the same diagram and must
       NOT touch the URL — the hash is the router's, and "#fl-…" would route to the
       landing page. It is an action on this page, so it is a button. */
    else if(r.kind==='flowref')  inner='<button type="button" class="tla-flowref" data-flow="'+esc(r.target)+'">'+wrap(esc(r.t),r)+'</button>';
    else                         inner=wrap(esc(r.t),r);
    if(r.v && !suppressNew){inner='<span class="tla-new" title="'+esc(t('addedin')+r.v)+'">'+inner+'</span>';}
    h+=inner;
  }
  return h;
}
function wrap(s,r){
  if(r.bold)s='<strong>'+s+'</strong>';
  if(r.italic)s='<em>'+s+'</em>';
  /* The Drowned City's alien script (tools/icons.py is_alien_font). Drawn with the book's own
     face rather than printed as the Latin letters underneath, which the reader is not meant to
     see — but the letters ARE the text, so they stay the element's content: they remain
     selectable, findable by the search box, and read out correctly, because the glyphs spell
     exactly those letters. The title says which script it is for anyone who hovers. */
  if(r.alien)s='<span class="tla-alien" title="'+esc(t('alienscript'))+'">'+s+'</span>';
  return s;
}
/* suppressNew: inside an entry that is itself brand new, every run would be
   flagged as added — which says nothing. The entry already carries its own
   "New vX" badge, so the per-run diff marks are suppressed there (the title
   does the same via titleHTML). */
/* noFaq: the chapter already carries the link this prose is pointing at, so the
   sentence must not sprout a second button to the same place. faqLink is a guess made
   from the wording — it fires on the Spanish lead here and not the English one — while
   a rebuilt chapter has the real thing off the page. The real thing wins. */
function blocksHTML(blocks,suppressNew,noFaq){
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
    else { h+='<p class="tla-p">'+runsHTML(b.runs,suppressNew)+'</p>'+(noFaq?'':faqLink(plainOfRuns(b.runs))); i++; }
  }
  return h;
}
/* The PDF shows a QR code to the retired-FAQ document after a sentence ending in
   a colon; render a real link instead. Which sentence that is depends on the
   language, so the pack says (ui.json -> "faqAnchor"). No anchor, no link. */
/* The landing section of the FAQ chapter 1 shelf (its first real section), for links
   that used to point at the retired-FAQ document on an external site. Null if this
   language has no FAQ corpus built. */
function faqHome(){
  var secs=(data&&data.sections)||[];
  for(var i=0;i<secs.length;i++){if(secs[i].corpus==='faq1'&&secs[i].kind!=='whatsnew')return secs[i].id;}
  return null;
}
/* The PDF shows a QR code to the retired-FAQ document after a sentence ending in a
   colon. That document now lives ON THIS SITE, as the FAQ chapter 1 shelf, so the link
   points there instead of off-site — an internal hash link, same tab. Which sentence
   triggers it depends on the language (ui.json -> "faqAnchor"); if no FAQ corpus is built
   the old external link is kept as a fallback. No anchor, no link. */
function faqLink(txt){
  var s=(txt||'').trim(), anchor=uiOf(lang,'faqAnchor',null);
  if(!anchor) return '';
  var re; try{ re=new RegExp(anchor,'i'); }catch(e){ return ''; }
  if(!re.test(s) || !/[:：]\s*$/.test(s)) return '';
  var home=faqHome();
  if(home){
    return '<a class="tla-extlink tla-faqlink" href="#'+esc(lang)+'/'+esc(home)+'">'
      +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>'
      +esc(t('faqlabel'))+'</a>';
  }
  if(!t('faqurl')) return '';
  return '<a class="tla-extlink" href="'+t('faqurl')+'" target="_blank" rel="noopener">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg>'
    +esc(t('faqlabel'))+'</a>';
}
function plainOfRuns(runs,L){var s='';for(var i=0;i<runs.length;i++){s+=runs[i].kind==='text'||runs[i].kind==='link'?runs[i].t:(' '+(pick(L||lang,'icons',runs[i].name)||'')+' ');}return s;}
function plainOfBlocks(blocks,L){return blocks.map(function(b){return plainOfRuns(b.runs,L);}).join(' ');}
function titleHTML(e){return e.titleRuns?runsHTML(e.titleRuns,true):esc(e.title);}
/* Same title with its links flattened, for a nav button or a contents link (see runsHTML). */
function titleFlat(e){return e.titleRuns?runsHTML(e.titleRuns,true,true):esc(e.title);}
/* An entry's history, as the data actually records it:
     addedIn    the edition it first appeared in
     changedIn  every later edition that rewrote part of it
   A badge is only shown for the newest edition — that is the "what changed"
   signal. The full provenance goes in a quieter line underneath. */
function latestV(){return (data.versions&&data.versions.length>1)?data.versions[data.versions.length-1].v:null;}
/* The edition the book starts from. Everything in it was "added" in it, so that is
   the baseline, not news — see verProvenance. */
function firstV(){return (data.versions&&data.versions.length)?data.versions[0].v:null;}
function isNewIn(e,v){return e.addedIn===v;}
function isChangedIn(e,v){return !!(e.changedIn&&e.changedIn.indexOf(v)>=0);}
function verBadge(e){
  var v=latestV(); if(!v)return '';
  if(isNewIn(e,v))return '<span class="tla-vbadge new" title="'+esc(t('addedin')+v)+'">'+esc(t('newbadge'))+' v'+esc(v)+'</span>';
  if(isChangedIn(e,v))return '<span class="tla-vbadge upd" title="'+esc(t('updatedin')+v)+'">'+esc(t('updbadge'))+' v'+esc(v)+'</span>';
  return '';
}
/* "Added in v1.1 · rewritten in v1.2" — shown on any entry with a history worth
   telling, so you can always see which edition brought which entry.
   Being in the FIRST edition is not a history: the whole book was added in it, so
   "Added in v1.0" was printed on 207 of the English book's 208 entries and told the
   reader nothing. It is suppressed — and nothing is lost, because "Rewritten in
   v1.1" already says the entry existed before v1.1. */
function verProvenance(e){
  if(!data.versions||data.versions.length<2)return '';
  var bits=[];
  if(e.addedIn&&e.addedIn!==firstV())bits.push(esc(t('addedinv').replace('{v}',e.addedIn)));
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
   mark, bold, an icon — in the one place that knows about them: runsHTML.

   `self` is the box's OWN number, and it is never linked: every box opens by naming
   itself ("Paso 1.1:"), and that is its label, not a reference. Linking it made 20 of
   this chapter's 23 marks scroll to where the reader already was. It went unnoticed
   because the mark was an <a> with no href, which nothing could focus or activate;
   the moment it became a real button it would have been 20 dead tab stops. */
function flowRuns(runs,nums,base,self){
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
      if(j%2===1 && nums[parts[j]] && parts[j]!==self){copy.kind='flowref'; copy.target=base+'-'+parts[j];}
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
    h+='<div class="tla-flow-box"'+id+'>'+runsHTML(flowRuns(b.runs,nums,base,it.n))+'</div>';
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

/* ---------- product icon reference ---------- */
/* The book prints this chapter as a list of small marks with a name beside each. As a
   photo of that page it could not be read, copied, searched or followed — and the QR
   beside it was a picture of a link. Rebuilt: the marks are the page's own vector art,
   the names are the pack's, and the QR is a real link.
   The art is masked, not <img>: an SVG loaded through <img> is an isolated document, so
   currentColor inside it resolves to its own black and the mark would vanish on a dark
   theme. As a mask it is painted by the page, like every other icon here. */
function prodIconHTML(it){
  return it.art ? '<span class="tla-prodicon" aria-hidden="true" style="-webkit-mask-image:url(assets/products/'
      +esc(it.art)+'.svg);mask-image:url(assets/products/'+esc(it.art)+'.svg)"></span>'
    : '<span class="tla-prodicon is-none" aria-hidden="true"></span>';
}
/* The one-page reference sheet, made consultable.
   The book prints its symbol key as coloured badges; on paper the colour is decoration,
   here it is data — so each symbol is drawn in its own class/skill/token colour rather
   than the theme's single ink. The groups are game-universal (the same five classes in
   every language), so the structure lives here and only the labels come from the pack.
   The page scan is kept underneath as a download, which is the whole sheet in one image. */
var QREF_GROUPS=[
  {key:'classes', names:['guardian','seeker','mystic','rogue','survivor']},
  {key:'skills',  names:['willpower','intellect','combat','agility','wild']},
  {key:'tokens',  names:['eldersign','autofail','skull','cultist','tablet','elderthing']}
];
function qrefSymbolCount(){var n=0; QREF_GROUPS.forEach(function(g){n+=g.names.length;}); return n;}
function symChip(name){
  /* The icon in its brand colour on a fixed light chip — the book's own device (a
     coloured mark on a light shield), and the reason the colour survives every theme:
     it is always read against the same chip, never against the page. */
  return '<span class="tla-symchip"><i class="ico ico-'+esc(name)+'" style="--icon:var(--sym-'+esc(name)+')"></i></span>';
}
function quickrefHTML(s){
  var h='<div class="tla-qref">';
  QREF_GROUPS.forEach(function(g){
    h+='<section class="tla-qref-grp" aria-labelledby="qr-'+g.key+'">';
    h+='<h2 class="tla-qref-h" id="qr-'+g.key+'">'+esc(t('qr'+g.key))+'</h2>';
    h+='<ul class="tla-symgrid">';
    g.names.forEach(function(n){
      h+='<li class="tla-symrow">'+symChip(n)
        +'<span class="tla-symname">'+esc(iconLabel(n))+'</span></li>';
    });
    h+='</ul></section>';
  });
  h+='</div>';
  return h;
}
function iconsHTML(s){
  var h='';
  if(s.qr){
    /* The book prints a QR because it is paper. This is not paper: the same target is
       a link you can click, middle-click, copy or have read aloud. */
    h+='<a class="tla-qrlink" href="'+esc(s.qr)+'" target="_blank" rel="noopener">'
      +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
      +'<path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg>'
      +esc(t('iconsqr'))+'</a>';
  }
  var gs=s.groups||[];
  gs.forEach(function(g,gi){
    var lvl=g.level||1;
    /* A heading with no icons of its own is only empty if nothing hangs under it. The
       encounter chapter nests — an expansion heading owns grids, and the grids own the
       icons — so "nothing here yet" on the parent would be a lie printed above
       twenty-three of them. */
    var parent=gi+1<gs.length && (gs[gi+1].level||1)>lvl;
    h+='<section class="tla-icongrp is-l'+lvl+'">';
    h+='<h'+(lvl+1)+' class="tla-icongrp-h">'+esc(g.title)+'</h'+(lvl+1)+'>';
    if(g.blurb)h+='<p class="tla-icongrp-d">'+esc(g.blurb)+'</p>';
    if(!g.items.length){
      /* The book ships these headings empty on purpose — the products are not out yet.
         Saying so is what the book does; dropping the group would tell the reader the
         game has fewer kinds of product than it has. */
      if(!parent)h+='<p class="tla-iconsoon">'+esc(t('iconsoon'))+'</p>';
    }else{
      h+='<ul class="tla-icontable">';
      g.items.forEach(function(it){
        /* Some rows are products the book left out of its table, filled in from the shared
           record (tools/packmap.py), and a couple are products no edition prints at all,
           added from our own sourced icons (packmap.EXTRAS). They render exactly like the
           printed rows — the site is a reference of the game, not a diff against one book. */
        h+='<li class="tla-iconrow">'+prodIconHTML(it)
          +(it.code?('<span class="tla-iconcode">'+esc(it.code)+'</span>'):'')
          +'<span class="tla-iconname">'+esc(it.name)+'</span>'
          +'</li>';
      });
      h+='</ul>';
    }
    h+='</section>';
  });
  return h;
}

/* The substitution table. The book draws it — two marks and an arrow per row — so on
   paper the only way to use it is to scan fourteen rows for the icon you hold. Here it
   is a real table you can filter, and every row is readable as a sentence, because the
   mark alone means nothing to anyone who cannot see it. */
function substMark(art){
  return art ? '<span class="tla-substmark" aria-hidden="true" style="-webkit-mask-image:url(assets/products/'
      +esc(art)+'.svg);mask-image:url(assets/products/'+esc(art)+'.svg)"></span>'
    : '<span class="tla-substmark is-none" aria-hidden="true"></span>';
}
function substCell(c){
  return '<span class="tla-substset">'+substMark(c.art)+'<span class="tla-substname">'+esc(c.label)+'</span></span>';
}
/* The book prints the operator as a bare "+" or "o" between two marks. A "+" read aloud
   is "plus", which is not what the row says, so the token stays visible exactly as the
   book sets it and the pack supplies the words underneath it. Which of the two a row is
   was decided by the page's geometry, not by the token: the book draws a tall brace for
   a row that fans out and a small arrow for one that does not. */
function substOp(op){
  var word=/^[^\W\d_]+$/.test(op)?'substany':'substall';
  return '<span class="tla-substop"><span aria-hidden="true">'+esc(op)+'</span>'
    +'<span class="tla-sr">'+esc(t(word))+'</span></span>';
}
function substHTML(e){
  var id='subst-'+esc(e.id);
  var h='<div class="tla-subst" data-subst="'+id+'">';
  h+='<div class="tla-substbar">'
    +'<label class="tla-substlab" for="'+id+'-q">'+esc(t('substfilter'))+'</label>'
    +'<input id="'+id+'-q" class="tla-substq" type="search" autocomplete="off" '
    +'placeholder="'+esc(t('substph'))+'">'
    +'<p class="tla-substcount" id="'+id+'-n" role="status" aria-live="polite"></p></div>';
  h+='<table class="tla-substtable" id="'+id+'-t"><thead><tr>'
    +'<th scope="col">'+esc(t('substfrom'))+'</th>'
    +'<th scope="col">'+esc(t('substto'))+'</th></tr></thead><tbody>';
  (e.table||[]).forEach(function(r,i){
    /* The row's identity is its place in the table, never its art: the book prints the
       same Midnight Masks mark on two different rows. */
    var hay=r.from.label+' '+r.to.map(function(c){return c.label;}).join(' ');
    h+='<tr class="tla-substrow" data-hay="'+esc(hay.toLowerCase())+'" data-i="'+i+'">';
    /* data-h carries the column header onto the cell: narrow screens drop the <thead>,
       and without it a stack of set names loses which side of the swap it is on. */
    h+='<td class="tla-substfrom" data-h="'+esc(t('substfrom'))+'">'+substCell(r.from)+'</td>';
    /* A row that fans out reads as two columns, like the book's own diagrams: the source
       centred on the left, the two (or more) replacements stacked on the right with the
       operator between them. A one-to-one row stays a single line. */
    var multi=r.to.length>1;
    h+='<td class="tla-substto'+(multi?' is-multi':'')+'" data-h="'+esc(t('substto'))+'">';
    r.to.forEach(function(c,j){
      if(j)h+=substOp(r.op||'+');
      h+=substCell(c);
    });
    h+='</td></tr>';
  });
  h+='</tbody></table>';
  h+='<p class="tla-substnone" hidden>'+esc(t('substnone'))+'</p>';
  h+='</div>';
  return h;
}
/* Filtering is done on the rows already in the DOM rather than by re-rendering: the
   marks are masked images, and re-rendering would flicker them on every keystroke. */
function substFilter(root){
  var q=root.querySelector('.tla-substq'), tb=root.querySelector('tbody');
  if(!q||!tb)return;
  var rows=[].slice.call(tb.querySelectorAll('.tla-substrow'));
  var count=root.querySelector('.tla-substcount'), none=root.querySelector('.tla-substnone');
  function run(){
    var v=q.value.trim().toLowerCase(), n=0;
    rows.forEach(function(tr){
      var hit=!v||tr.getAttribute('data-hay').indexOf(v)>=0;
      tr.hidden=!hit; if(hit)n++;
    });
    none.hidden=!!n;
    /* Silent while untouched: a count announced on load is noise, and the table is
       right there. It only speaks once the reader has actually filtered. */
    count.textContent=v?(n+' '+t('of')+' '+rows.length+' '+plural('substrows',rows.length)):'';
  }
  q.addEventListener('input',run);
  run();
}

function extLinkIcon(){
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
    +'<path d="M14 3h7v7"/><path d="M21 3l-9 9"/>'
    +'<path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg>';
}
/* The book ends a sentence with a colon and prints a QR, because it is paper. This is
   not paper: the same target is a link you can click, copy or have read aloud. */
function qrLinkHTML(e){
  if(!e.qr)return '';
  return '<a class="tla-qrlink" href="'+esc(e.qr)+'" target="_blank" rel="noopener">'
    +extLinkIcon()+esc(t('printplay'))+'</a>';
}
/* Material the book does not have, that this language's pack adds.
   Fenced and attributed, always. A reader has to be able to tell what FFG published from
   what a community did — so this never blends into the prose above it, it names its
   source in its own heading, and it says outright that it is not part of the Grimoire.
   That the block is Spanish-only is not enforced here: only the Spanish pack declares
   any, so only Spanish has any to show. */
function extrasHTML(e){
  var x=e.extras;
  if(!x||!x.items||!x.items.length)return '';
  var h='<aside class="tla-extras" aria-labelledby="ex-'+esc(e.id)+'">';
  h+='<p class="tla-extras-h" id="ex-'+esc(e.id)+'">'
    +'<span class="tla-extras-tag">'+esc(t('extrastag'))+'</span> '
    +esc(t('extrasby').replace('{s}',x.source))+'</p>';
  h+='<p class="tla-extras-d">'+esc(t('extrasnote'))+'</p>';
  h+='<ul class="tla-extras-l">';
  x.items.forEach(function(it){
    h+='<li><a href="'+esc(it.url)+'" target="_blank" rel="noopener">'+extLinkIcon()+esc(it.title)+'</a>';
    if(it.note)h+='<span class="tla-extras-n">'+esc(it.note)+'</span>';
    h+='</li>';
  });
  return h+'</ul></aside>';
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
var THEMES=['slate','moss','midnight','plum','neon','parchment','fog'];
/* The default is named, not THEMES[0]: the array's order is the PICKER's order, and
   which theme comes first in a list has nothing to do with which one a new reader
   should land on. Keep in step with index.html's pre-paint script. */
var DEFTHEME='midnight';
var OLDTHEMES={light:'parchment',dark:'midnight'};   // what the two-theme toggle saved
function themeName(id){return pick(lang,'themes',id)||id;}
function currentTheme(){
  var t=document.documentElement.getAttribute('data-theme');
  if(OLDTHEMES[t])t=OLDTHEMES[t];
  return THEMES.indexOf(t)>=0?t:DEFTHEME;
}
function applyThemeLabel(){
  if(elTheme)elTheme.setAttribute('aria-label',t('themetip')+': '+themeName(currentTheme()));
}
function setTheme(th){
  if(THEMES.indexOf(th)<0)th=DEFTHEME;
  document.documentElement.setAttribute('data-theme',th);
  try{localStorage.setItem('tla-theme',th);}catch(e){}
  applyThemeLabel(); markTheme();
}
/* Six themes are worth nothing if nobody finds the palette button. So it says so —
   once, on a first visit, and never again. Dismissed by opening the picker (the
   point was made), by the close button, or by choosing a theme.
   Not a modal, not a blocker, and not shown to someone who already has a theme
   saved: they have plainly found it. */
function themeTipSeen(){
  try{return !!localStorage.getItem('tla-themetip')||!!localStorage.getItem('tla-theme');}catch(e){return true;}
}
function dropThemeTip(){
  var el=document.getElementById('tla-themetip');
  if(el&&el.parentNode)el.parentNode.removeChild(el);
  try{localStorage.setItem('tla-themetip','1');}catch(e){}
}
function showThemeTip(){
  if(themeTipSeen())return;
  var wrap=document.querySelector('.tla-themewrap'); if(!wrap)return;
  var d=document.createElement('div');
  d.className='tla-themetip'; d.id='tla-themetip';
  /* role=status, not alert: this is an offer, not a problem, and it must not
     interrupt whatever a screen reader is already saying. */
  d.setAttribute('role','status');
  d.innerHTML='<span class="tla-themetip-t">'+esc(t('themetip1'))+'</span>'
    +'<button class="tla-themetip-x" type="button" aria-label="'+esc(t('close'))+'">×</button>';
  wrap.appendChild(d);
  d.querySelector('.tla-themetip-x').addEventListener('click',function(e){e.stopPropagation(); dropThemeTip();});
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
  dropThemeTip();                     // they found it; stop saying so
  buildThemePicker();
  elThemeMenu.hidden=false; elTheme.setAttribute('aria-expanded','true');
  clampHeaderMenu(elThemeMenu, elThemeMenu.closest('.tla-themewrap'));
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
    if(s.kind==='whatsnew'||s.kind==='intro')return;       // not content to search
    var corpus=s.corpus||'grimoire';
    if(s.intro&&s.intro.length){arr.push({corpus:corpus,sid:s.id,eid:s.id,title:s.title,sec:s.title,num:s.num,text:plainOfBlocks(s.intro,L),isSec:true});}
    (s.entries||[]).forEach(function(e){arr.push({corpus:corpus,sid:s.id,eid:e.id,title:e.title,titleRuns:e.titleRuns,sec:s.title,num:s.num,text:plainOfBlocks(e.blocks,L)});});
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
/* Languages whose newest edition is newer than this one's, newest first. No
   language is "the source": whoever is ahead is ahead. `corpus` picks which document's
   versions to compare — the grimoire (v/date) or the FAQ chapter 1 (faqV/faqDate) — so
   the FAQ's own "a newer edition exists elsewhere" notice reads the FAQ's versions.
   Returns normalised {code, v, date} so callers read the same fields either way. */
function langsAhead(code,corpus){
  var vf=(corpus==='faq1')?'faqV':'v', df=(corpus==='faq1')?'faqDate':'date';
  var meL=regOf(code)||{}, me=meL[vf]; if(!me)return [];
  return LANGS.filter(function(L){return L.code!==code && L[vf] && cmpV(L[vf],me)>0;})
              .sort(function(a,b){return cmpV(b[vf],a[vf]);})
              .map(function(L){return {code:L.code,v:L[vf],date:L[df]};});
}
function normalizeData(g){
  var li=latestInfo(g);
  /* The chapter also exists when this language has no news of its own but another
     language does — that IS the news. */
  if((li||langsAhead(g.lang).length) && !g.sections.some(function(x){return x.id==='novedades';})){
    /* group: this chapter is built here rather than declared, so unlike every other
       section it has no pack to say which shelf it belongs on — and it is the book's
       own news, so it belongs on the book's. Not a hardcoded list of keys: the object
       is made here, so its shelf travels with it exactly as its kind does. */
    g.sections.splice(1,0,{num:'',key:'whatsnew',id:'novedades',kind:'whatsnew',group:'grimoire',
      title:pick(g.lang,'strings','news')||'What\'s New',ver:li,intro:[],entries:[],figures:[]});
  }
}
/* Splice the FAQ chapter 1 corpus into the grimoire's section list as its own shelf.
   Kept as one merged sections[] so routing, the nav, findEntry and the search index all
   work unchanged — the corpus is carried on each section (s.corpus) for the few places
   that must tell the two apart: the split search, the corpus-scoped What's New, and the
   fact that links only ever point INTO the grimoire, never into this retired corpus.
   Idempotent: a re-load must not splice it twice. */
function mergeFaq(g, faq){
  g.sections.forEach(function(s){ if(!s.corpus)s.corpus='grimoire'; });
  if(!faq || g._faqMerged) return;
  var fsecs=faq.sections.map(function(s){ s.corpus='faq1'; if(!s.group)s.group='chapter1'; return s; });
  /* The FAQ has its own version history and its own "What's New": a base-version corpus
     (one version, no diff) shows none yet, exactly as the grimoire would — the machinery
     is here and ready for the day a new FAQ edition lands. It carries its own versions/
     whatsnew so renderWhatsNew reads the right corpus. */
  var li=latestInfo(faq);
  if(li && !fsecs.some(function(x){return x.id==='faq-novedades';})){
    fsecs.unshift({num:'',key:'faq-whatsnew',id:'faq-novedades',kind:'whatsnew',group:'chapter1',
      corpus:'faq1',title:pick(g.lang,'strings','news')||'What\'s New',ver:li,
      corpusVersions:faq.versions,corpusWhatsnew:faq.whatsnew,intro:[],entries:[],figures:[]});
  }
  /* the FAQ shelf sits directly below the grimoire's */
  var go=(g.groupOrder||['resources','grimoire','aids']).slice();
  if(go.indexOf('chapter1')<0){ var gi=go.indexOf('grimoire'); go.splice(gi>=0?gi+1:go.length,0,'chapter1'); g.groupOrder=go; }
  g.sections=g.sections.concat(fsecs);
  g._faqMerged=true;
}
/* Hang the interactive taboo list (built from ArkhamDB) on the FAQ chapter-1 taboo chapter
   (key "faq-taboos"): it renders as a per-card index — name, collection, icon, a direct ArkhamDB
   link — above the chapter's own full Spanish text. The Resources "taboos" section is left as its
   placeholder for the richer viewer to come. No taboo data -> nothing changes. Idempotent. */
function attachTaboos(g, taboo){
  if(!g||!taboo)return;
  for(var i=0;i<g.sections.length;i++){
    if(g.sections[i].key==='faq-taboos'){ g.sections[i].taboos=taboo; break; }
  }
}
/* The taboo CARD viewer's section (distinct from the FAQ's taboo LIST above). The reserved
   "taboos" section in the grimoire ships as a "coming soon" placeholder; once its card reprints
   are loaded — the language's own, or the English ones with a beta flag — it turns into the real
   viewer. No cards -> the placeholder stays. Idempotent. */
function attachTabooCards(g, tc){
  if(!g||!tc||!tc.cards||!tc.cards.length)return;
  for(var i=0;i<g.sections.length;i++){
    if(g.sections[i].key==='taboos'){
      g.sections[i].kind='taboocards';
      g.sections[i].tabooCards=tc.cards;
      g.sections[i].tabooBeta=!!tc.beta;
      /* On a borrowed shell (a UI-only language) the section is flagged nobook; the taboo cards
         ARE its content, in English behind a beta notice, so it is not book-less after all. */
      g.sections[i].nobook=false;
      break;
    }
  }
}
/* A language's taboo card reprints: its own file if it declares one, else the English file with a
   beta flag, so every language can open the section (uncovered ones see English + a notice).
   Best-effort — null on failure leaves the section a placeholder. */
function loadTabooCards(reg, L){
  if(TABOOCARDS[L])return Promise.resolve(TABOOCARDS[L]);
  var own=reg&&reg.tabooCardsData;
  return getJSON(own||'data/taboo_cards_en.json').then(function(c){
    return {cards:c, beta:!own};
  },function(){return null;});
}
/* the nav badge counts what the newest edition brought — in whichever corpus the
   What's New section belongs to (the FAQ carries its own history). */
function wnCount(s){var w=(s.corpusWhatsnew||data.whatsnew); var wn=s.ver&&w&&w[s.ver.v]; return wn?(wn['new'].length+wn.updated.length):0;}

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
/* ---------- diagrams-only view ---------- */
/* The book draws each phase twice: as prose, and as the flowchart that summarises
   it. Readers who know the rules want the summary — so a chapter that has diagrams
   can be reduced to just them.

   A plain boolean, NOT a tri-state like azOpen. azOpen is tri-state because the
   *screen* has an opinion (27 letters eat a third of a phone), so `null` means "not
   asked, let the viewport answer". Nothing has an opinion about whether a reader
   wants the prose, so there is nothing to defer to: it is "everything" until asked.

   Not persisted, and not in the URL. Only identity (tla-lang) and appearance
   (tla-theme) outlive a session; a view that hides three quarters of a chapter must
   not greet a reader who has forgotten choosing it, and a shared link must not hand
   that to someone who never did. */
/* Which cut of the chapter is on screen: 'all', 'diag' (only what the book draws) or
   'fanmade' (only the community's deeper diagram, where a chapter has one). One value rather
   than a pair of booleans, because they are one question with one answer. */
var docView='all';
function diagOnly(){return docView==='diag';}
function fmOnly(){return docView==='fanmade';}
/* Which chapters offer it: the ones that actually draw something. Keyed off e.flow —
   never off the title, the index, or the "-2" id suffix, because the book inverts
   the pair on the Upkeep phase (there the flow entry comes first). */
function hasDiagrams(s){return sectionEntries(s).some(function(e){return !!e.flow;});}
function visibleEntries(s){
  var all=sectionEntries(s);
  /* First, and composing with the others rather than replacing them: "the glossary
     entries under R that v1.1 touched" is a reasonable thing to ask for, and the two
     filters are about different axes. */
  if(verOnly)all=all.filter(function(e){return inVer(e,verOnly);});
  if(s.kind==='glossary' && glossFilter!=='all'){return all.filter(function(e){return entryLetter(e)===glossFilter;});}
  if(fmOnly())return [];
  if(diagOnly() && hasDiagrams(s)){return all.filter(function(e){return !!e.flow;});}
  return all;
}

/* Two named alternatives, one choice: native radios in a fieldset — the same shape
   of question as the theme picker, and the same answer.
   Not role=switch: a switch is on/off and must be named for what it controls, so it
   could only be "Solo diagramas" + a state, dropping "Ver todo" as a named place to
   go. Not aria-expanded: nothing is revealed, the document itself changes. Not two
   aria-pressed buttons: that announces two unrelated toggles and never says they are
   one choice of two. The fieldset gives group semantics, "1 of 2", arrow keys and a
   single tab stop for free — authored by the browser, so not authorable wrong. */
/* The segmented pill lives in its own row inside the fieldset, and the fieldset
   carries no border. A <legend> is not a flex item: the browser lays it INTO the
   top border, whatever display it is given — which is why the label sat half over
   the frame. Borderless fieldset, legend as an ordinary line above, and the row
   owns the frame. Same shape as the theme picker, for the same reason. */
/* ---------- version filter (any chapter) ----------
   The book is a living document, so "what changed in v1.1?" is a question about every
   chapter, not only about the What's New list. It is also the answer to the FAQ: once a
   chapter holds eighty questions, "the twelve that are new" is the only way in.

   Only offered where it can mean something: a language with one edition has nothing to
   compare, and the FIRST edition is never an option — everything is "added" in it, so
   filtering by it would show the whole chapter under a name that promises less. Today
   that means the filter shows in en and not in es, which is not a gap but the truth:
   es has only ever had v1.0. */
var verOnly=null;              // null = show everything
function verOptions(s){
  var f=firstV(), have={};
  sectionEntries(s).forEach(function(e){
    if(e.addedIn)have[e.addedIn]=1;
    if(e.changedIn)e.changedIn.forEach(function(v){have[v]=1;});
  });
  /* The pack's own version order, newest first — never a string sort, which would put
     v1.10 before v1.9. */
  return (data.versions||[]).map(function(x){return x.v;})
    .filter(function(v){return v!==f && have[v];}).reverse();
}
function inVer(e,v){return isNewIn(e,v)||isChangedIn(e,v);}
function verSwitch(s){
  var opts=verOptions(s);
  if(!opts.length)return '';
  var h='<fieldset class="tla-diagpick tla-verpick"><legend class="tla-diagpick-lg">'+esc(t('viewas'))+'</legend>';
  h+='<div class="tla-diagpick-row">';
  var all=[['',t('all')]].concat(opts.map(function(v){return [v,t('vernew').replace('{v}',v)];}));
  all.forEach(function(o){
    var on=(o[0]||null)===verOnly;
    h+='<label class="tla-diagopt"><input type="radio" name="tla-verview" value="'+esc(o[0])+'"'
      +(on?' checked':'')+'><span>'+esc(o[1])+'</span></label>';
  });
  return h+'</div></fieldset>';
}
function setVerOnly(v){
  v=v||null;
  if(verOnly===v)return;
  verOnly=v;
  render(curSec.id,null,false); elMain.scrollTop=0;
  /* render() destroyed the radio that was just pressed; focus its replacement, or the
     reader is dropped at the top of the document. Same reason setDocView re-focuses. */
  var again=elMain.querySelector('.tla-verpick input[value="'+(v||'')+'"]');
  if(again){try{again.focus();}catch(e){}}
  var n=visibleEntries(curSec).length;
  announce((verOnly?t('vernew').replace('{v}',verOnly):t('all'))+': '+n+' '+plural('entries',n));
}
/* The options this chapter offers. A chapter the community has diagrammed more deeply
   (tools/fanmade.py) offers three cuts instead of two — and then "diagrams only" is named for
   whose diagram it is, so the reader is never left wondering which one they are looking at. */
function diagOptions(s){
  if(s&&s.fanmade)return [['all',t('viewall')],['diag',t('fmofficial')],['fanmade',t('fmfanmade')]];
  return [['all',t('viewall')],['diag',t('viewdiag')]];
}
function diagSwitch(s){
  var h='<fieldset class="tla-diagpick"><legend class="tla-diagpick-lg">'+esc(t('viewdiagrams'))+'</legend>';
  h+='<div class="tla-diagpick-row">';
  diagOptions(s).forEach(function(o){
    var on=o[0]===docView;
    h+='<label class="tla-diagopt"><input type="radio" name="tla-diagview" value="'+esc(o[0])+'"'
      +(on?' checked':'')+'><span>'+esc(o[1])+'</span></label>';
  });
  return h+'</div></fieldset>';
}
function setDocView(v){
  if(docView===v)return;
  docView=v;
  var on=v==='diag';
  render(curSec.id,null,false);
  /* render() destroyed the radio that was just pressed; focus its replacement, or
     the reader is dropped at the top of the document. Same reason the edition chips
     re-focus at the What's New handler. */
  var again=elMain.querySelector('.tla-diagpick input[value="'+v+'"]');
  if(again){try{again.focus();}catch(e){}}
  /* The page silently rewrote itself underneath a screen reader, so say what it now
     holds — and count DIAGRAMS, not entries. Entries are the wrong axis: a chapter
     that is one long lead plus a single diagram would announce "1 of 1 entries",
     reporting that nothing happened, right after 27 blocks of rules text vanished.
     What the reader asked for is diagrams, so that is what is counted. */
  var shown=visibleEntries(curSec).length;
  var lbl=(diagOptions(curSec).filter(function(o){return o[0]===v;})[0]||[0,v])[1];
  announce(on?(lbl+': '+shown+' '+plural('diagrams',shown)):lbl);
}

/* ---------- NAV ---------- */
/* The shelves the site files its sections under, in the order the pack first mentions
   one. Read from the data, never a list of keys held here: the site is growing past the
   book, and which shelf a thing sits on is the pack's to say. A section with no group
   (the intro) comes first and stands outside them all. */
function navGroups(){
  var out=[], by={};
  data.sections.forEach(function(s,si){
    var g=s.group||'';
    if(!by[g]){by[g]={id:g, items:[]}; out.push(by[g]);}
    by[g].items.push({s:s, si:si});
  });
  /* Shelf order is the pack's to set (data.groupOrder), so "Recursos before the Grimoire"
     is a data change, not a code one. The ungrouped home link stays pinned at the top;
     a group the order forgot to mention falls to the end rather than vanishing. */
  var order=data.groupOrder||[];
  out.sort(function(a,b){
    if(!a.id)return -1; if(!b.id)return 1;
    var ia=order.indexOf(a.id), ib=order.indexOf(b.id);
    return (ia<0?99:ia)-(ib<0?99:ib);
  });
  return out;
}
function buildNav(){
  var h='';
  navGroups().forEach(function(g){
    /* Each shelf collapses, so a reader can fold the whole Grimoire away to reach
       Recursos or Ayudas. Native <details>: keyboard-operable and announced as
       expandable for free. Collapsed by default now that there are four shelves — markNav
       opens the one holding the section you are on, so you always see where you are. The
       heading stays a real h2 inside the summary, so the outline is unbroken and the
       labelled group semantics hold. */
    if(g.id){
      h+='<details class="tla-navgrp">';
      h+='<summary class="tla-nav-grp-s"><h2 class="tla-nav-grp" id="navgrp-'+esc(g.id)+'">'+esc(t('grp'+g.id))+'</h2></summary>';
      h+='<div class="tla-nav-grpbody" role="group" aria-labelledby="navgrp-'+esc(g.id)+'">';
    }
    h+=navItems(g.items);
    if(g.id)h+='</div></details>';
  });
  elNav.innerHTML=h;
}
function navItems(items){
  var h=''; items.forEach(function(it){
    var s=it.s, si=it.si;
    var news=s.kind==='whatsnew';
    var soon=s.kind==='placeholder';
    var n=sectionEntries(s).length;
    var num=news?'<span class="tla-nav-num"><i class="tla-eldersign" aria-hidden="true"></i></span>'
                :(s.num?('<span class="tla-nav-num">'+esc(s.num)+'</span>'):'<span class="tla-nav-num">•</span>');
    var wc=news?wnCount(s):0;
    /* A placeholder counts nothing, so it shows the word instead of a number — otherwise
       it reads as a chapter that happens to be empty rather than one not written yet. */
    var cnt=soon?('<span class="tla-nav-cnt is-soon">'+esc(t('soon'))+'</span>')
          :news?(wc?('<span class="tla-nav-cnt new">'+wc+'</span>'):''):(n?('<span class="tla-nav-cnt">'+n+'</span>'):'');
    h+='<div class="tla-nav-sec'+(news?' is-news':'')+(soon?' is-soon':'')+'" data-si="'+si+'" id="navsec-'+s.id+'">';
    h+='<button class="tla-nav-btn" type="button" data-si="'+si+'">'+num+'<span>'+esc(s.title)+'</span>'+cnt+'</button>';
    if(s.kind!=='glossary' && n){
      var subs=sectionEntries(s).filter(inToc);
      if(subs.length){
        h+='<div class="tla-sublist">';
        subs.forEach(function(e){h+='<button class="tla-sublink" type="button" data-eid="'+esc(e.id)+'">'+titleFlat(e)+diagBadge(e)+'</button>';});
        h+='</div>';
      }
    }
    h+='</div>';
  });
  return h;
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
/* The set the A-Z bar works over: all the glossary's entries, but narrowed by the
   version filter when one is on — so the two filters compose. Without this the bar
   offers letters that have no entries under the active version (a dead button that
   filters to nothing), and the tally counts entries the version filter has hidden. */
function glossBase(s){
  return verOnly ? sectionEntries(s).filter(function(e){return inVer(e,verOnly);}) : sectionEntries(s);
}
function azSummary(s){
  var total=glossBase(s).length, shown=visibleEntries(s).length;
  /* Folded, this line is the only thing saying a filter is on at all — so it
     names the letter, not just the tally. */
  return glossFilter==='all' ? (total+' '+plural('entries',total))
       : (glossFilter+' · '+shown+' '+t('of')+' '+total+' '+plural('entries',total));
}
function azFilterBar(s){
  var present={}; glossBase(s).forEach(function(e){present[entryLetter(e)]=1;});
  /* An active letter the version filter just emptied is no longer offered, so drop back
     to "all" rather than leave a highlighted letter showing nothing. */
  if(glossFilter!=='all' && !present[glossFilter])glossFilter='all';
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
  /* render() destroyed the letter button that was just pressed; focus its replacement,
     or a keyboard reader is dropped at the top of the document — the same guard
     setVerOnly and setDocView already carry. */
  var again=elMain.querySelector('.tla-azbtn[data-az="'+cssEsc(v)+'"]');
  if(again){try{again.focus();}catch(e){}}
  var n=visibleEntries(curSec).length;
  announce((v==='all'?t('all'):v)+': '+n+' '+plural('entries',n));
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

/* ---------- Ultimatums & Boons viewer ----------
   A card gallery built from the optional-rules chapter: three category tabs and,
   under the open one, a master list beside the chosen card. The item text is the
   grimoire's own rule — which for a non-English reader is the translation the
   English card picture cannot give them. State (open tab, chosen card per tab)
   is kept in module vars so a language switch or a return to the section lands
   where it left, falling back to the first card when a slug is gone in the new
   language. */
var UB_TABS=['ultimatum','boon','refraction'];
var ubTab='ultimatum';
var ubSel={};
/* How the viewer shows a tab: 'list' (a sidebar list + one large card, as before) or
   'gallery' (every card at once, 5argon-style). Remembered across the session. */
var ubView=(function(){try{return localStorage.getItem('tla-ubview')==='gallery'?'gallery':'list';}catch(e){return 'list';}})();
var ubBleed=false;   // download UB cards with a print bleed margin, chosen in the download modal
/* The frame "skin": v1 is 5argon's clean frame (default), v2 the textured one. Only the frame over
   the art differs; the art and the live text are the same. The picture set swaps by folder. */
var ubSkin=(function(){try{return localStorage.getItem('tla-ubskin')==='v2'?'v2':'v1';}catch(e){return 'v1';}})();
function ubCardSrc(it){ return ubSkin==='v2'?('ub/cards-v2/'+it.slug+'.webp'):it.card; }
function ubThumbSrc(it){ return ubSkin==='v2'?('ub/thumbs-v2/'+it.slug+'.webp'):it.thumb; }
/* Which chapter's cards to show: 'all', 'cap1' (the retired FAQ — many more refractions) or
   'cap2' (the 2026 Grimoire). Ultimatums and boons are the same in both, so they are tagged
   'both' and show under any filter; only the refractions differ. Remembered for the session. */
var ubChap=(function(){try{var v=localStorage.getItem('tla-ubchap'); return (v==='cap1'||v==='cap2')?v:'all';}catch(e){return 'all';}})();
function ubChapOK(it){return ubChap==='all'||!it.chapter||it.chapter==='both'||it.chapter===ubChap;}
/* The shared half of every Ultimatums/Boons/Refractions card, loaded once. */
var UBREG=null;
/* Put a language's cards back together: the card's own facts (picture, illustrator,
   encounter-set and campaign symbols, chapter) from the shared registry, the language's
   words on top. Done once per language at load time, so every reader of s.ub below sees
   exactly the record it always saw and nothing else in the viewer had to change. Runs
   safely more than once, and does nothing at all when there is no registry. */
function hydrateUB(g){
  if(!g||!UBREG||!UBREG.cards)return;
  (g.sections||[]).forEach(function(s){
    if(!s||s.kind!=='ultimatums'||!s.ub)return;
    ['ultimatums','boons','refractions'].forEach(function(b){
      var a=s.ub[b];if(!a)return;
      a.forEach(function(rec){
        var shared=UBREG.cards[rec.slug];if(!shared)return;
        for(var k in shared){if(!Object.prototype.hasOwnProperty.call(rec,k))rec[k]=shared[k];}
      });
    });
  });
}
function ubBucket(s,cat){var ub=s&&s.ub||{}; var a=cat==='ultimatum'?(ub.ultimatums||[]):cat==='boon'?(ub.boons||[]):(ub.refractions||[]); return a.filter(ubChapOK);}
/* Whether the corpus even has both chapters' cards (the FAQ was built) — the filter is only
   worth showing then. */
function ubHasChapters(s){var ub=s&&s.ub||{}; return (ub.refractions||[]).some(function(it){return it.chapter==='cap1';});}
/* Refraction-only filters: narrow by campaign, then by a scenario within it. Selecting either
   forces the chapter filter to 'all' (so the two cuts never fight). Transient — a way to answer
   "which refractions apply to my scenario?" — so not remembered across sessions. */
var ubCampaign='', ubScenario='';
/* A refraction is itself either an ultimatum (it makes the game harder) or a boon (it makes it
   easier), so the refractions panel can be cut that way too: 'all', 'ultimatum' or 'boon'.
   Remembered like the chapter filter — it is a lasting preference ("show me only the boons"),
   not a one-off question. */
var ubType=(function(){try{var v=localStorage.getItem('tla-ubtype'); return (v==='ultimatum'||v==='boon')?v:'all';}catch(e){return 'all';}})();
function ubTypeOK(it){return ubType==='all'||it.cat===ubType;}
/* The refractions to show: the chapter bucket, then the ultimatum/boon cut, then (campaign
   picked) that campaign, then (scenario picked too) the campaign-wide ones plus that one
   scenario's specific ones. */
function ubRefracList(s){
  var a=ubBucket(s,'refraction').filter(ubTypeOK);
  if(ubCampaign){
    a=a.filter(function(r){var p=ubRefractionParts(r); return !!(p&&p.campaign===ubCampaign);});
    if(ubScenario)a=a.filter(function(r){var p=ubRefractionParts(r); return !!(p&&(!p.scenario||p.scenario===ubScenario));});
  }
  return a;
}
/* Display items for a tab: refractions also honour the campaign/scenario filter. */
function ubItems(s,cat){return cat==='refraction'?ubRefracList(s):ubBucket(s,cat);}
/* Every refraction (chapter-independent): the campaign/scenario filter forces the chapter to
   'all' anyway, so its options offer every campaign, not just the current chapter's. */
function ubAllRefractions(s){return (s&&s.ub&&s.ub.refractions)||[];}
/* Distinct campaigns present in the refractions, in campaign (first-seen) order. */
function ubCampaignList(s){
  var seen={}, out=[];
  ubAllRefractions(s).forEach(function(r){var p=ubRefractionParts(r); var c=p&&p.campaign; if(c&&!seen[c]){seen[c]=1; out.push(c);}});
  return out;
}
/* Distinct scenarios of the chosen campaign that carry a scenario-specific refraction. */
function ubScenarioList(s){
  if(!ubCampaign)return [];
  var seen={}, out=[];
  ubAllRefractions(s).forEach(function(r){
    var p=ubRefractionParts(r); if(!p||p.campaign!==ubCampaign)return;
    var sc=p.scenario; if(sc&&!seen[sc]){seen[sc]=1; out.push(sc);}
  });
  return out;
}
/* A small chapter tag on a refraction (Cap. 1 / Cap. 2), shown only when the corpus carries both
   chapters — so a single-chapter viewer is not littered with the same tag on every card. */
function ubChapChip(it){
  if(!curSec||!ubHasChapters(curSec))return '';
  var ch=it&&it.chapter;
  if(ch!=='cap1'&&ch!=='cap2')return '';
  return '<span class="tla-ub-chip tla-chip-'+ch+'">'+esc(t('ubchap'+ch))+'</span>';
}
/* The refractions panel's own filter bar: the chapter toggle (moved here from the viewer-wide
   tools, since only refractions differ by chapter) plus a campaign selector and, once a campaign
   is chosen, a scenario selector — the way a player asks "which refractions apply to my scenario?"
   A clear button resets all three to their defaults. */
function ubRefracFilterBar(s){
  var h='<div class="tla-ub-rfilter">';
  if(ubHasChapters(s)){
    h+='<div class="tla-ub-fgroup">'
      +'<span class="tla-ub-flabel" id="ubchap-lbl">'+esc(t('ubchaplabel'))+'</span>'
      +'<div class="tla-ub-chap" role="group" aria-labelledby="ubchap-lbl">';
    ['all','cap1','cap2'].forEach(function(ch){
      var on=ubChap===ch;
      h+='<button type="button" class="tla-ub-chapbtn'+(on?' is-on':'')+'" data-ubchap="'+ch+'" aria-pressed="'+on+'">'+esc(t('ubchap'+ch))+'</button>';
    });
    h+='</div></div>';
  }
  /* Ultimatum or boon: the same segmented control as the chapter, because it answers the same
     kind of question — "narrow this list" — and the two read as one row of filters. */
  h+='<div class="tla-ub-fgroup">'
    +'<span class="tla-ub-flabel" id="ubtype-lbl">'+esc(t('ubtypelabel'))+'</span>'
    +'<div class="tla-ub-chap" role="group" aria-labelledby="ubtype-lbl">';
  [['all','ubtypeall'],['ultimatum','ubultimatums'],['boon','ubboons']].forEach(function(p){
    var on=ubType===p[0];
    h+='<button type="button" class="tla-ub-chapbtn'+(on?' is-on':'')+'" data-ubtype="'+p[0]+'" aria-pressed="'+on+'">'+esc(t(p[1]))+'</button>';
  });
  h+='</div></div>';
  var camps=ubCampaignList(s);
  if(camps.length){
    var scens=ubScenarioList(s);
    h+='<label class="tla-ub-sel"><span class="tla-ub-flabel">'+esc(t('refrcampaign'))+'</span>'
      +'<select class="tla-ub-selbox" data-ubcamp><option value="">'+esc(t('ubcampall'))+'</option>';
    camps.forEach(function(c){h+='<option value="'+esc(c)+'"'+(c===ubCampaign?' selected':'')+'>'+esc(c)+'</option>';});
    h+='</select></label>';
    h+='<label class="tla-ub-sel"><span class="tla-ub-flabel">'+esc(t('refrscenario'))+'</span>'
      +'<select class="tla-ub-selbox" data-ubscen'+((ubCampaign&&scens.length)?'':' disabled')+'><option value="">'+esc(t('ubscenall'))+'</option>';
    scens.forEach(function(sc){h+='<option value="'+esc(sc)+'"'+(sc===ubScenario?' selected':'')+'>'+esc(sc)+'</option>';});
    h+='</select></label>';
    if(ubCampaign||ubScenario||ubChap!=='all'||ubType!=='all'){
      h+='<button type="button" class="tla-ub-clear" data-ubclear>'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'
        +esc(t('ubclearfilter'))+'</button>';
    }
  }
  h+='</div>';
  return h;
}
function ubFindItem(s,cat,slug){var a=ubItems(s,cat); for(var i=0;i<a.length;i++)if(a[i].slug===slug)return a[i]; return null;}
function ubIndexOf(s,cat,slug){var a=ubItems(s,cat); for(var i=0;i<a.length;i++)if(a[i].slug===slug)return i; return -1;}
/* Step through the shown cards without going back to the list — the way you would leaf through
   a physical stack. List mode only: the gallery already has every card on screen at once, so an
   arrow there would mean nothing. The end of the stack disables its arrow rather than wrapping
   around, so the reader can feel where the list ends. */
function ubStepperHTML(s,cat,sel){
  if(ubView!=='list')return '';
  var a=ubItems(s,cat), i=ubIndexOf(s,cat,sel);
  if(i<0||a.length<2)return '';
  function btn(d,key,path){
    var off=(d<0)?(i<=0):(i>=a.length-1);
    return '<button type="button" class="tla-ub-stepbtn" data-ubstep="'+d+'"'+(off?' disabled':'')
      +' aria-label="'+esc(t(key))+'" title="'+esc(t(key))+'">'
      +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="'+path+'"/></svg></button>';
  }
  return '<div class="tla-ub-step">'+btn(-1,'ubprev','m15 18-6-6 6-6')
    +'<span class="tla-ub-stepn">'+esc(t('ubpos').replace('{i}',i+1).replace('{n}',a.length))+'</span>'
    +btn(1,'ubnext','m9 18 6-6-6-6')+'</div>';
}
/* What sits in the list view's right-hand pane: the card, and the stepper under it. Built in
   one place because picking a name replaces the whole pane. */
function ubPaneHTML(s,cat,sel){return ubDetailHTML(ubFindItem(s,cat,sel))+ubStepperHTML(s,cat,sel);}
function ubLabel(cat){return t(cat==='ultimatum'?'ubultimatums':cat==='boon'?'ubboons':'ubrefractions');}
function ubChosen(s,cat){
  var a=ubItems(s,cat); if(!a.length)return null;
  var want=ubSel[cat];
  for(var i=0;i<a.length;i++)if(a[i].slug===want)return want;
  ubSel[cat]=a[0].slug; return a[0].slug;
}
function ubTypeLine(it){
  var base=t(it.cat==='boon'?'ubtypeboon':'ubtypeultimatum');
  return it.refraction?base+' '+t('ubtyperefraction'):base;
}
/* An item English has but this language does not yet: shown in English, flagged
   above the card with the version it arrived in (the changelog carries the rest). */
function ubPendingHTML(it){
  var msg=it.sinceVer?t('ubpendingv').replace('{v}',it.sinceVer):t('ubpending');
  return '<div class="tla-ub-pending">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
    +'<circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>'
    +'<span>'+esc(msg)+'</span></div>';
}
/* A masked SVG symbol drawn in the card's cream: encounter-set and product marks are
   the same two-colour art the icon chapters recolour through a CSS mask. */
function ubSymHTML(art,cls){
  return '<span class="tla-ubc-sym'+(cls?' '+cls:'')+'" aria-hidden="true" style="-webkit-mask-image:url(assets/products/'
    +esc(art)+'.svg);mask-image:url(assets/products/'+esc(art)+'.svg)"></span>';
}
/* A refraction belongs to a scenario and, through it, to a campaign — both named on the
   real card, each beside its symbol. The subtitle line the book prints reads
   "{scenario} ({campaign})", so split on the parenthesis and put the encounter-set symbol
   before the scenario and the collection (box) symbol before the campaign. Any other
   subtitle (or a shape we do not recognise) renders as plain runs, unchanged. */
/* A refraction affects a whole campaign, or a single scenario within one. The Grimoire's
   subtitle reads "{scenario} ({word} {campaign})" (or just a campaign phrase), so split it
   into named parts: the collection symbol marks the campaign, the encounter-set symbol the
   scenario. The campaign word ("campaña"/"campaign") is stripped so the name stands alone.
   Returns null for any subtitle shape we do not recognise. */
function ubRefractionParts(it){
  if(!it.refraction)return null;
  var scenario=it.scenario||'', campaign=it.campaign||'';
  if(!campaign){
    /* Fallback for a refraction that carries no split fields (the Grimoire's own Scorched
       Earth): read the "{scenario} ({word} {campaign})" subtitle the book prints. */
    var runs=it.subtitle;
    if(!(runs&&runs.length===1&&runs[0].kind==='text'))return null;
    var txt=(runs[0].t||'').trim(); campaign=txt;
    var m=txt.match(/^(.*?)\s*\(([^)]*)\)\s*$/);
    if(m){ scenario=m[1].trim(); campaign=m[2].trim(); }
    var word=t('refrcampaignword');
    /* The word is stripped so the name can stand alone under the label the UI prints. It can
       lead the name ("campaña Hermanos de las cenizas"), trail it ("Brethren of Ash Campaign")
       or — in German — be welded onto it as a compound with a hyphen and no space at all
       ("„Bruderschaft der Asche“-Kampagne"). Requiring whitespace missed that last form, so the
       German card read "Kampagne „Bruderschaft der Asche“-Kampagne", saying it twice. */
    if(word){var wx=word.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
      campaign=campaign.replace(new RegExp('^'+wx+'\\s+|[-\\s\\u2010-\\u2015]+'+wx+'$','i'),'').trim();}
  }
  if(!campaign)return null;
  /* The scenario name shows even when its encounter-set symbol is not known (the FAQ has no
     per-scenario icon table); the campaign symbol comes from the FAQ's campaign-icon table. */
  return {scenario:scenario, campaign:campaign, hasScenario:!!scenario,
          setIcon:it.set||'', collIcon:it.collection||''};
}
/* Card subtitle: the scenario (with its set symbol), then the campaign (with its collection
   symbol) as "Campaign X" — capital C. A campaign-wide refraction shows only "Campaign X". */
function ubSubtitleHTML(it){
  var p=ubRefractionParts(it);
  if(p){
    var h='';
    if(p.hasScenario){
      h+='<span class="tla-ubc-subpart">'+(p.setIcon?ubSymHTML(p.setIcon,'tla-ubc-subsym'):'')+'<span class="tla-ubc-subtxt">'+esc(p.scenario)+'</span></span>'
        +'<span class="tla-ubc-subsep" aria-hidden="true">·</span>';
    }
    h+='<span class="tla-ubc-subpart">'+(p.collIcon?ubSymHTML(p.collIcon,'tla-ubc-subsym'):'')+'<span class="tla-ubc-subtxt">'+esc(t('refrcampaign')+' '+p.campaign)+'</span></span>';
    return h;
  }
  return runsHTML(it.subtitle,true);
}
function ubDetailHTML(it){
  if(!it)return '';
  /* The card is built from layers: the textless picture, then the title, type line
     and rule over it. When the text is the English fallback it is tagged lang="en" so
     a screen reader switches voice, and the banner says why. */
  var L=it.pending?' lang="en"':'';
  var h=it.pending?ubPendingHTML(it):'';
  h+='<div class="tla-ubc'+(it.noart?' is-noart':'')+(it.refraction?' is-refraction':'')+'" data-slug="'+esc(it.slug)+'" data-cat="'+esc(it.cat||'')+'">';
  h+='<img class="tla-ubc-pic" src="assets/'+esc(ubCardSrc(it))+'" width="'+it.w+'" height="'+it.h+'" alt="" draggable="false" crossorigin="anonymous">';
  h+='<button type="button" class="tla-ubc-dl" data-ubdl aria-label="'+esc(t('ubdownload'))+'" title="'+esc(t('ubdownload'))+'">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg></button>';
  if(it.noart)h+='<div class="tla-ubc-noart">'+esc(t('ubnoart'))+'</div>';
  h+='<h2 class="tla-ubc-title"'+L+'>'+esc(it.name)+'</h2>';
  /* A refraction's subtitle names its encounter set, centred under the title; its set
     symbol sits in the diamond above the type line, and its product symbol in the bottom
     corner — where the printed card carries each. */
  if(it.subtitle&&it.subtitle.length){
    h+='<div class="tla-ubc-subtitle"'+L+'>'+ubSubtitleHTML(it)+'</div>';
  }
  if(it.set)h+='<div class="tla-ubc-setmark">'+ubSymHTML(it.set)+'</div>';
  h+='<div class="tla-ubc-type">'+esc(ubTypeLine(it))+'</div>';
  h+='<div class="tla-ubc-rule"'+L+'>'+blocksHTML(it.blocks,true,true)+'</div>';
  if(it.collection)h+='<div class="tla-ubc-coll">'+ubSymHTML(it.collection)+'</div>';
  if(it.illus)h+='<div class="tla-ubc-illus">'+esc(t('ubillus'))+' '+esc(it.illus)+'</div>';
  h+='</div>';
  return h;
}
/* Shrink a rule that would overflow its box until it fits. Because the box and the
   font both scale with the card's width (container-query units), the fitted ratio is
   the same at every display size, so this is computed once per card. */
function ubFit(rule){
  if(!rule)return;
  var set=function(f){rule.style.setProperty('--ubfit',f);};
  var fits=function(){return rule.scrollHeight<=rule.clientHeight+1;};
  set(1); if(fits())return;
  var lo=0.55,hi=1,best=0.55;
  for(var i=0;i<8;i++){var m=(lo+hi)/2; set(m); if(fits()){best=m;lo=m;}else{hi=m;}}
  set(best);
}
/* Fit the auto-sized rule of a card (its box and font both scale with the card width). */
function ubFitCard(card){
  if(!card)return;
  ubFit(card.querySelector('.tla-ubc-rule'));
}
function ubFitVisible(root){
  var cards=(root||elMain).querySelectorAll('.tla-ub-panel:not([hidden]) .tla-ubc');
  [].forEach.call(cards,function(c){ubFitCard(c);});
}
/* Force the card fonts to actually load before we paint to a canvas. document.fonts.ready
   only waits for loads a painted element already triggered — an off-screen card may not
   trigger them, so canvas fillText would silently fall back to a serif. Loading each face
   explicitly (and awaiting) guarantees the blackletter title and Arno body render as seen.
   Also makes the auto-fit measure with the real metrics, so the sizes match too. */
var UB_FONT_SPECS=['40px ubtitle','40px ubbody','700 40px ubbody','italic 40px ubbody','italic 700 40px ubbody'];
function ubFontsReady(){
  var d=window.document&&document.fonts;
  if(!d||!d.load)return Promise.resolve();
  // Load each face (specs kept lenient — 'ubtitle' declares no weight), then wait for the
  // font set to settle, then warm the canvas cache so the first fillText already has them.
  return Promise.all(UB_FONT_SPECS.map(function(f){return d.load(f);}))
    .then(function(){return d.ready;})
    .then(function(){
      try{var c=document.createElement('canvas').getContext('2d');
        UB_FONT_SPECS.forEach(function(f){c.font=f;c.fillText(' ',-20,-20);});}catch(e){}
    }).catch(function(){});
}
/* A filesystem-safe file name from the card's own (translated) name: refractions carry
   the translated "Refraction" word in front, as the reader asked. */
function ubRefractionWord(){return t('ubtyperefraction').replace(/[.]+$/,'').trim();}
function ubSanitizeName(n){return (n||'card').replace(/[\/\\:*?"<>|]+/g,'').replace(/\s+/g,' ').trim();}
/* The translated folder a card goes in inside the "download all" zip — Ultimatums, Boons or
   Refractions, each its tab's own name, so the archive sorts itself the way the viewer does. */
function ubFolderName(it){return ubSanitizeName(it.refraction?t('ubrefractions'):it.cat==='boon'?t('ubboons'):t('ubultimatums'));}
/* The download variant, spelled into the file name so a reader can tell copies apart: the bleed
   choice (i18n) and, for UB, the frame skin (V1/V2 — a skin id, not translated). */
function ubVariantSuffix(){ return ' - '+(ubBleed?t('tbwithbleed'):t('tbnobleed'))+' - '+ubSkin.toUpperCase(); }
/* Draw the shown card onto a canvas at a fixed width, in the reader's language, square
   (no rounded corners). Each text layer's real position and font are read off the DOM, so
   the wrapping and the auto-fit size come out as seen. Same-origin picture and symbols, so
   the canvas stays untainted. Resolves to a PNG Blob (null if the picture is not ready). */
function ubCardToBlob(card,mime,quality){
  return new Promise(function(resolve){
    if(!card){resolve(null);return;}
    var img=card.querySelector('.tla-ubc-pic'); if(!img||!img.naturalWidth){resolve(null);return;}
    var slug=card.getAttribute('data-slug')||'';
    ubFontsReady().then(function(){
    /* With bleed, draw the FULL-bleed textless plate (its 60/91 px margin is real frame art) scaled
       so its trim lands on the 1000px box, exactly like the taboo export — never a pixel stretch. */
    (ubBleed?loadImg('assets/ub/cards'+(ubSkin==='v2'?'-v2':'')+'-bleed/'+slug+'.webp'):Promise.resolve(null)).then(function(full){
      var CW=1000, CH=Math.round(CW*img.naturalHeight/img.naturalWidth);
      var cr=card.getBoundingClientRect(), sc=CW/cr.width;
      var useBleed=!!(ubBleed&&full&&full.naturalWidth);
      var cv=document.createElement('canvas'), ctx, X, Y;
      if(useBleed){
        var mx=Math.round(60*CW/1312), my=Math.round(91*CH/1818);
        cv.width=CW+2*mx; cv.height=CH+2*my; ctx=cv.getContext('2d');
        ctx.drawImage(full,0,0,cv.width,cv.height);
        X=function(px){return mx+(px-cr.left)*sc;}; Y=function(py){return my+(py-cr.top)*sc;};
      }else{
        cv.width=CW; cv.height=CH; ctx=cv.getContext('2d');
        ctx.drawImage(img,0,0,CW,CH);
        X=function(px){return (px-cr.left)*sc;}; Y=function(py){return (py-cr.top)*sc;};
      }
      var outline=function(fs){ctx.lineJoin='round'; ctx.strokeStyle='rgba(0,0,0,.92)'; ctx.lineWidth=Math.max(1,fs*0.16);};
      function line(el){
        if(!el)return; var t=(el.textContent||'').trim(); if(!t)return;
        var r=el.getBoundingClientRect(), s=getComputedStyle(el), fs=parseFloat(s.fontSize)*sc;
        ctx.font=s.fontStyle+' '+s.fontWeight+' '+fs+'px '+s.fontFamily;
        ctx.fillStyle=s.color; ctx.textBaseline='middle'; outline(fs);
        var cen=s.textAlign==='center', x=cen?X(r.left+r.width/2):X(r.left), y=Y(r.top+r.height/2);
        ctx.textAlign=cen?'center':'left';
        ctx.strokeText(t,x,y); ctx.fillText(t,x,y);
      }
      function para(el){
        if(!el)return; var t=(el.textContent||'').replace(/\s+/g,' ').trim(); if(!t)return;
        var r=el.getBoundingClientRect(), s=getComputedStyle(el);
        var fs=parseFloat(s.fontSize)*sc, lh=parseFloat(s.lineHeight)*sc||fs*1.3, bw=r.width*sc;
        ctx.font='normal '+s.fontWeight+' '+fs+'px '+s.fontFamily;
        ctx.fillStyle=s.color; ctx.textAlign='left'; ctx.textBaseline='top'; outline(fs);
        var words=t.split(' '), ln='', out=[];
        words.forEach(function(w){var tt=ln?ln+' '+w:w; if(ln&&ctx.measureText(tt).width>bw){out.push(ln);ln=w;}else ln=tt;});
        if(ln)out.push(ln);
        var x=X(r.left), y=Y(r.top);
        out.forEach(function(l){ctx.strokeText(l,x,y); ctx.fillText(l,x,y); y+=lh;});
      }
      line(card.querySelector('.tla-ubc-title'));
      /* The subtitle flows text and inline symbols; draw each text span at its own place so
         the symbols (drawn below with the other marks) land between them, as on screen. */
      var subtxts=card.querySelectorAll('.tla-ubc-subtitle .tla-ubc-subtxt,.tla-ubc-subtitle .tla-ubc-subsep');
      if(subtxts.length){ [].forEach.call(subtxts,line); }
      else line(card.querySelector('.tla-ubc-subtitle'));
      line(card.querySelector('.tla-ubc-type'));
      line(card.querySelector('.tla-ubc-illus'));
      line(card.querySelector('.tla-ubc-noart'));
      para(card.querySelector('.tla-ubc-rule'));
      var syms=[].slice.call(card.querySelectorAll('.tla-ubc-setmark .tla-ubc-sym,.tla-ubc-coll .tla-ubc-sym,.tla-ubc-subtitle .tla-ubc-sym'));
      Promise.all(syms.map(function(sy){
        return new Promise(function(res){
          var s=getComputedStyle(sy), m=s.maskImage||s.webkitMaskImage||'';
          var url=(m.match(/url\(["']?([^"')]+)/)||[])[1]; if(!url){res();return;}
          var r=sy.getBoundingClientRect(), w=Math.max(1,r.width*sc), h=Math.max(1,r.height*sc);
          var im=new Image();
          im.onload=function(){
            var tc=document.createElement('canvas'); tc.width=w; tc.height=h;
            var tx=tc.getContext('2d'); tx.drawImage(im,0,0,w,h);
            tx.globalCompositeOperation='source-in'; tx.fillStyle='#f4ecd8'; tx.fillRect(0,0,w,h);
            ctx.drawImage(tc,X(r.left),Y(r.top)); res();
          };
          im.onerror=function(){res();}; im.src=url;
        });
      })).then(function(){
        /* Fallback to the old edge-clamp only if the full-bleed plate is missing. */
        var out=(ubBleed&&!useBleed)?addBleed(cv):cv;
        out.toBlob(function(b){resolve(b);},mime||'image/png',quality);
      });
    });
    });
  });
}
/* Trigger a browser download of a blob under the given filename. */
function ubSaveBlob(b,name){
  if(!b)return;
  var a=document.createElement('a'); a.href=URL.createObjectURL(b);
  a.download=name; document.body.appendChild(a); a.click();
  document.body.removeChild(a); setTimeout(function(){URL.revokeObjectURL(a.href);},1500);
}
/* Load a same-origin image; resolves to the decoded <img> (or null). */
function loadImg(url){
  return new Promise(function(res){
    var im=new Image(); im.crossOrigin='anonymous';
    im.onload=function(){res(im);}; im.onerror=function(){res(null);}; im.src=url;
  });
}
/* Add a print bleed to a rendered card canvas: ~3mm all round (4.7% of the width, 3.4% of the
   height), the margin filled by EXTENDING each edge -- the outermost pixel strip stretched outward,
   the corners clamped -- so the frame runs off the trim cleanly, without duplicating card content
   the way a scale-to-cover fill does. Keeps front and back the same size with no bespoke bleed art. */
function addBleed(src){
  var W=src.width, H=src.height, mx=Math.round(W*0.047), my=Math.round(H*0.034);
  var cv=document.createElement('canvas'); cv.width=W+2*mx; cv.height=H+2*my;
  var c=cv.getContext('2d');
  c.drawImage(src, 0,0,1,1,        0,0,       mx,my);   // top-left corner
  c.drawImage(src, 0,0,W,1,        mx,0,      W,my);    // top edge
  c.drawImage(src, W-1,0,1,1,      mx+W,0,    mx,my);   // top-right corner
  c.drawImage(src, 0,0,1,H,        0,my,      mx,H);    // left edge
  c.drawImage(src, W-1,0,1,H,      mx+W,my,   mx,H);    // right edge
  c.drawImage(src, 0,H-1,1,1,      0,my+H,    mx,my);   // bottom-left corner
  c.drawImage(src, 0,H-1,W,1,      mx,my+H,   W,my);    // bottom edge
  c.drawImage(src, W-1,H-1,1,1,    mx+W,my+H, mx,my);   // bottom-right corner
  c.drawImage(src, mx,my);                              // the sharp trim in the middle
  return cv;
}
/* Rotate a canvas by a multiple of 90 degrees (clockwise). Investigators are printed landscape but
   drawn as a landscape plate, so the download is turned upright: the front a quarter-turn, the back
   three quarter-turns, which leaves the two 180 apart for a flip-on-the-long-edge duplex print. */
function rotateCanvas(src, deg){
  deg=((deg%360)+360)%360; if(!deg)return src;
  var swap=(deg%180)!==0, w=swap?src.height:src.width, h=swap?src.width:src.height;
  var cv=document.createElement('canvas'); cv.width=w; cv.height=h;
  var c=cv.getContext('2d');
  c.translate(w/2,h/2); c.rotate(deg*Math.PI/180); c.drawImage(src,-src.width/2,-src.height/2);
  return cv;
}
/* A flat image (a card BACK) as a PNG blob, optionally with a print bleed. Null if it will not load. */
function imageToPngBlob(url, bleed){
  return loadImg(url).then(function(im){
    if(!im||!im.naturalWidth)return null;
    var cv=document.createElement('canvas'); cv.width=im.naturalWidth; cv.height=im.naturalHeight;
    cv.getContext('2d').drawImage(im,0,0);
    if(bleed)cv=addBleed(cv);
    return new Promise(function(res){ cv.toBlob(function(b){res(b);},'image/png'); });
  });
}
/* The UB set has two card backs: one for ultimatums, one for boons (a refraction is a boon),
   each in the two frame skins — the no-bleed back follows ubSkin just like the bleed one below. */
function ubBackType(catOrIt){ var c=(catOrIt&&catOrIt.cat)||catOrIt; return c==='ultimatum'?'ultimatum':'boon'; }
function ubBackUrl(type){ return 'assets/ub/backs/'+type+(ubSkin==='v2'?'-v2':'')+'.webp'; }
function ubBackLabel(type){ return (type==='ultimatum'?t('ubultimatums'):t('ubboons'))+' — '+t('tbback'); }
/* A flat image as a blob at the given mime (the UB no-bleed back). Null if it will not load. */
function imageBlob(url, mime, quality){
  return loadImg(url).then(function(im){
    if(!im||!im.naturalWidth)return null;
    var cv=document.createElement('canvas'); cv.width=im.naturalWidth; cv.height=im.naturalHeight;
    cv.getContext('2d').drawImage(im,0,0);
    return new Promise(function(res){ cv.toBlob(function(b){res(b);}, mime||'image/png', quality); });
  });
}
/* The UB card back as a blob. Without bleed, the trimmed back 1:1. WITH bleed, the FULL-bleed back of
   the CURRENT skin, scaled so its trim lands where the front's does — same final size as the front
   for duplex, with the margin the back's own art, never an edge stretch. */
function ubBackBlob(type, mime, quality){
  if(!ubBleed) return imageBlob(ubBackUrl(type), mime, quality);
  return loadImg('assets/ub/backs-bleed/'+type+(ubSkin==='v2'?'-v2':'')+'.webp').then(function(full){
    if(!full||!full.naturalWidth) return imageToPngBlob(ubBackUrl(type), true);   // last resort: stretch
    var CW=1000, CH=1386, mx=Math.round(60*CW/1312), my=Math.round(91*CH/1818);
    var cv=document.createElement('canvas'); cv.width=CW+2*mx; cv.height=CH+2*my;
    cv.getContext('2d').drawImage(full,0,0,cv.width,cv.height);
    return new Promise(function(res){ cv.toBlob(function(b){res(b);}, mime||'image/png', quality); });
  });
}
/* Names in the taboo shape — card "…_01", its back "…_02" — inside the card's translated folder. */
function ubCardExportName(card, side){
  var name=((card.querySelector('.tla-ubc-title')||{}).textContent||'card');
  var cat=card.getAttribute('data-cat'), refraction=card.classList.contains('is-refraction');
  var folder=ubSanitizeName(refraction?t('ubrefractions'):cat==='boon'?t('ubboons'):t('ubultimatums'));
  if(refraction)name=ubRefractionWord()+' - '+name;
  return folder+'/'+ubSanitizeName(name+ubVariantSuffix())+(side==='back'?'_02':'_01');
}
function ubItemExportName(it, side){
  return ubFolderName(it)+'/'+ubSanitizeName(it.name+ubVariantSuffix())+(side==='back'?'_02':'_01');
}
/* Download one card and its back — the card as _01, the back as _02, in the taboo order. */
function ubDownload(card){
  if(!card)return;
  var type=ubBackType(card.getAttribute('data-cat'));
  ubCardToBlob(card).then(function(b){ if(b)ubSaveBlob(b, ubCardExportName(card,'card')+'.png'); });
  ubBackBlob(type,'image/png').then(function(b){ if(b)ubSaveBlob(b, ubCardExportName(card,'back')+'.png'); });
}
/* ---- minimal STORE-mode ZIP writer (no deps): PNGs are already compressed, so
   storing them uncompressed keeps the archive small and the code tiny. ---- */
var _crcTable=null;
function crc32(bytes){
  if(!_crcTable){_crcTable=[];for(var n=0;n<256;n++){var c=n;for(var k=0;k<8;k++)c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1);_crcTable[n]=c>>>0;}}
  var c=0xFFFFFFFF;
  for(var i=0;i<bytes.length;i++)c=_crcTable[(c^bytes[i])&0xFF]^(c>>>8);
  return (c^0xFFFFFFFF)>>>0;
}
function ubZip(files){
  var enc=new TextEncoder(), parts=[], central=[], offset=0;
  var FLAG=0x0800;                                   // bit 11: file names are UTF-8 (accents)
  var u16=function(n){return [n&0xFF,(n>>>8)&0xFF];};
  var u32=function(n){return [n&0xFF,(n>>>8)&0xFF,(n>>>16)&0xFF,(n>>>24)&0xFF];};
  files.forEach(function(f){
    var name=enc.encode(f.name), data=f.data, crc=crc32(data), n=data.length;
    var lh=[].concat(u32(0x04034b50),u16(20),u16(FLAG),u16(0),u16(0),u16(0),u32(crc),u32(n),u32(n),u16(name.length),u16(0));
    parts.push(new Uint8Array(lh),name,data);
    var cd=[].concat(u32(0x02014b50),u16(20),u16(20),u16(FLAG),u16(0),u16(0),u16(0),u32(crc),u32(n),u32(n),
      u16(name.length),u16(0),u16(0),u16(0),u16(0),u32(0),u32(offset));
    central.push(new Uint8Array(cd),name);
    offset+=lh.length+name.length+n;
  });
  var csize=0; central.forEach(function(c){csize+=c.length;});
  var end=new Uint8Array([].concat(u32(0x06054b50),u16(0),u16(0),u16(files.length),u16(files.length),u32(csize),u32(offset),u16(0)));
  return new Blob(parts.concat(central,[end]),{type:'application/zip'});
}
/* Every card of the current section, across all three buckets. */
function ubAllItems(){
  var s=curSec, out=[];
  UB_TABS.forEach(function(cat){ ubBucket(s,cat).forEach(function(it){out.push(it);}); });
  return out;
}
/* Render one card into an off-screen host (kept in layout so getBoundingClientRect and
   the container-query sizing are real) and resolve once its picture is decoded + fitted. */
function ubRenderOffscreen(it,host){
  host.innerHTML=ubDetailHTML(it);
  var card=host.querySelector('.tla-ubc'), img=card.querySelector('.tla-ubc-pic');
  return new Promise(function(res){
    var done=function(){ ubFitCard(card); res(card); };
    if(img.complete&&img.naturalWidth)done();
    else{img.onload=done; img.onerror=done;}
  });
}
/* Render a list of cards CONCURRENTLY, up to `conc` at a time, instead of strictly one-by-one.
   The whole export runs in the visitor's own browser — the server only ships static WebP plates,
   so "many people downloading at once" never adds server compute; each browser draws its own cards.
   The per-visitor wait was the real cost, and it is dominated by each card's plate fetch + decode,
   which overlap when several run together. `worker(item,idx)` returns a Promise; a rejected one is
   swallowed so one bad card can't sink the archive. `onEach` fires after every card for progress. */
function renderPool(items, worker, conc, onEach){
  conc=Math.max(1, conc||4);
  var i=0, active=0;
  return new Promise(function(resolve){
    if(!items.length){resolve();return;}
    function pump(){
      while(active<conc && i<items.length){
        active++;
        /* IIFE to capture idx by VALUE — a plain `var idx` is function-scoped, so every task in the
           first synchronous batch would close over the same (final) idx and all render the same item,
           leaving the earlier slots null. */
        (function(idx){
          Promise.resolve().then(function(){return worker(items[idx],idx);})
            .catch(function(){})
            .then(function(){ active--; if(onEach)try{onEach();}catch(e){}
              if(i>=items.length && active===0)resolve(); else pump(); });
        })(i++);
      }
    }
    pump();
  });
}
/* Download every card of the section as a single .zip, in the selected language. Cards are
   rendered off-screen at the card's natural max width, several at a time, so the PNGs match
   what the viewer shows. */
function ubDownloadAll(btn){
  var items=ubAllItems(); if(!items.length)return;
  var label=btn&&btn.querySelector('.tla-ub-tool-label'), orig=label?label.textContent:'';
  if(btn){btn.disabled=true; btn.setAttribute('aria-busy','true'); if(label)label.textContent=t('ubdownallwait');}
  /* Two entries per card, interleaved: the card as _01 then its own back as _02 — the taboo order,
     so each card is immediately followed by its back (many copies of the shared back, as asked). */
  var entries=[]; items.forEach(function(it){ entries.push({it:it,side:'card'}); entries.push({it:it,side:'back'}); });
  var slots=new Array(entries.length), total=entries.length, done=0;
  var tick=function(){ done++; if(label)label.textContent=done+' / '+total; };
  var finish=function(){ if(btn){btn.disabled=false; btn.removeAttribute('aria-busy'); if(label)label.textContent=orig;} };
  /* The back is identical per back-type (+ the chosen bleed/skin), so render each once and reuse the
     bytes under every card's own back-name instead of re-encoding it for all ~90. */
  var backCache={};
  var backBytes=function(type){ if(!backCache[type])backCache[type]=ubBackBlob(type,'image/jpeg',0.95).then(function(b){return b?b.arrayBuffer().then(function(ab){return new Uint8Array(ab);}):null;}); return backCache[type]; };
  /* Each concurrent card render gets its OWN off-screen host inside #tla-root (the card's
     `font-family:'ubtitle',var(--ff-head)` depends on --ff-head, defined there; under document.body
     that var is undefined and the title falls back to the body serif). */
  ubFontsReady().then(function(){
    return renderPool(entries, function(ent,idx){
      var it=ent.it, nm=ubItemExportName(it,ent.side)+'.jpg';
      if(ent.side==='back') return backBytes(ubBackType(it)).then(function(u8){ if(u8)slots[idx]={name:nm, data:u8}; });
      var host=document.createElement('div');
      host.style.cssText='position:fixed;left:-10000px;top:0;width:460px;pointer-events:none';
      (root||document.body).appendChild(host);
      var clean=function(){ try{(root||document.body).removeChild(host);}catch(e){} };
      return ubRenderOffscreen(it,host)
        .then(function(card){return ubCardToBlob(card,'image/jpeg',0.95);})
        .then(function(b){ if(b)return b.arrayBuffer().then(function(ab){slots[idx]={name:nm, data:new Uint8Array(ab)};}); })
        .then(clean, function(e){ clean(); throw e; });
    }, 4, tick);
  }).then(function(){ finish(); var files=slots.filter(Boolean); if(files.length)ubSaveBlob(ubZip(files),'the-living-arkham-ultimatums-'+lang+'-'+ubSkin+(ubBleed?'-bleed':'-nobleed')+'.zip'); })
    .catch(function(){ finish(); });
}
/* Fisher-Yates: take n distinct items from arr at random (Math.random is fine client-side). */
function ubSample(arr,n){
  var a=arr.slice(); n=Math.max(0,Math.min(n,a.length));
  for(var i=0;i<n;i++){var j=i+Math.floor(Math.random()*(a.length-i)); var tmp=a[i];a[i]=a[j];a[j]=tmp;}
  return a.slice(0,n);
}
/* The hand on screen: [{cat, picks:[item,…]}, …] in the order the groups are shown. Held
   rather than left in the DOM because a single card can be redrawn, and the replacement has
   to know what the rest of the hand already holds. */
var ubDrawn=null;
/* Draw nu random ultimatums + nb random boons: a short readable list first, then the live
   cards below it. Called from the draw modal's form. */
function ubDrawRun(){
  var s=curSec, out=document.getElementById('tla-ubdraw-out'); if(!out)return;
  var uMax=ubBucket(s,'ultimatum').length, bMax=ubBucket(s,'boon').length;
  var uEl=document.getElementById('tla-ubdraw-u'), bEl=document.getElementById('tla-ubdraw-b');
  var nu=Math.max(0,Math.min(parseInt(uEl.value,10)||0,uMax));
  var nb=Math.max(0,Math.min(parseInt(bEl.value,10)||0,bMax));
  uEl.value=nu; bEl.value=nb;
  if(nu+nb===0){ ubDrawn=null; out.innerHTML='<p class="tla-ubdraw-empty" role="alert">'+esc(t('ubdrawempty'))+'</p>'; return; }
  /* One group per kind, so ultimatums and boons read apart: each a panelled block with a
     quick name list and, below it, the drawn cards (large, and zoomable on click). */
  ubDrawn=[{cat:'ultimatum',picks:ubSample(ubBucket(s,'ultimatum'),nu)},
           {cat:'boon',picks:ubSample(ubBucket(s,'boon'),nb)}]
          .filter(function(g){return g.picks.length;});
  ubDrawPaint('.tla-ubdraw-h');
}
/* Redraw one card in place: another from the same bucket, never one the hand already holds
   (otherwise "draw another" could hand back a duplicate, or the same card again). Silent when
   the hand already holds the whole bucket — the button is disabled in that case anyway. */
function ubDrawSwap(gi,ci){
  var g=ubDrawn&&ubDrawn[gi]; if(!g||!g.picks[ci])return;
  var held={}; g.picks.forEach(function(it){held[it.slug]=1;});
  var pool=ubBucket(curSec,g.cat).filter(function(it){return !held[it.slug];});
  if(!pool.length)return;
  g.picks[ci]=ubSample(pool,1)[0];
  /* Repaint the lot, not just the one card: the name list above the cards is part of the
     same hand and would otherwise go stale. Focus goes back to the button just pressed, so
     redrawing twice running does not send the reader back to the heading. */
  ubDrawPaint('[data-ubswap="'+gi+':'+ci+'"]');
}
/* Paint ubDrawn into the modal, then focus whatever focusSel names. */
function ubDrawPaint(focusSel){
  var out=document.getElementById('tla-ubdraw-out'); if(!out||!ubDrawn)return;
  var h='';
  ubDrawn.forEach(function(g,gi){
    /* Nothing left to swap in once the hand holds the whole bucket. */
    var spare=ubBucket(curSec,g.cat).length>g.picks.length;
    h+='<section class="tla-ubdraw-group">';
    h+='<h3 class="tla-ubdraw-h"'+(gi===0?' tabindex="-1"':'')+'>'+esc(ubLabel(g.cat))
      +' <span class="tla-ubdraw-n">'+g.picks.length+'</span></h3>';
    h+='<ol class="tla-ubdraw-list">';
    g.picks.forEach(function(it){
      h+='<li'+(it.pending?' lang="en"':'')+'><b>'+esc(it.name)+'</b>'
        +(it.pending?' <span class="tla-ub-en" title="'+esc(t('ubpending'))+'">EN</span>':'')+'</li>';
    });
    h+='</ol><div class="tla-ubdraw-cards">';
    g.picks.forEach(function(it,ci){
      h+='<div class="tla-ubdraw-card">'+ubDetailHTML(it)
        +'<button type="button" class="tla-ubdraw-swap" data-ubswap="'+gi+':'+ci+'"'
        +(spare?'':' disabled title="'+esc(t('ubdrawswapnone'))+'"')+'>'
        +esc(t('ubdrawswap'))+'</button></div>';
    });
    h+='</div></section>';
  });
  out.innerHTML=h;
  var fit=function(){ [].forEach.call(out.querySelectorAll('.tla-ubc'),function(c){ubFitCard(c);}); };
  fit();
  if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit).catch(function(){});
  var f=focusSel&&out.querySelector(focusSel); if(f){try{f.focus();}catch(e){}}
}
/* Zoom a drawn card: render it (art + live text) to a PNG and open it big in the shared
   image lightbox, so the rule reads at full size. */
var ubZoomURL=null;
function ubZoomCard(card){
  if(!card)return;
  ubCardToBlob(card).then(function(b){
    if(!b)return;
    if(ubZoomURL)try{URL.revokeObjectURL(ubZoomURL);}catch(e){}
    ubZoomURL=URL.createObjectURL(b);
    openLightbox(ubZoomURL,(card.querySelector('.tla-ubc-title')||{}).textContent||'');
  });
}
function ubHTML(s){
  if(UB_TABS.indexOf(ubTab)<0)ubTab='ultimatum';
  /* The intro names the Optional Rules chapter these cards are read from — as a link,
     found by the shared key so it lands right in every language. */
  var opt=data.sections.filter(function(x){return x.key==='optional-rules';})[0];
  var lead=esc(t('ubintro')).replace('{opt}', opt
    ?'«<a class="xref" href="#'+esc(lang)+'/'+esc(opt.id)+'" data-t="'+esc(opt.id)+'">'+esc(opt.title)+'</a>»'
    :'');
  var h='<div class="tla-lead"><p class="tla-p">'+lead+'</p></div>';
  h+='<div class="tla-ub">';
  /* Viewer-wide tools: draw a random hand, or download every card as a .zip. */
  h+='<div class="tla-ub-tools">';
  h+='<button type="button" class="tla-ub-tool" id="ubdraw-open">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
    +'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/>'
    +'<circle cx="15.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/><circle cx="8.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>'
    +'<circle cx="15.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/></svg>'
    +'<span>'+esc(t('ubdraw'))+'</span></button>';
  h+='<button type="button" class="tla-ub-tool" id="ubdownall" title="'+esc(t('ubdownalltip'))+'">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
    +'<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>'
    +'<span class="tla-ub-tool-label">'+esc(t('ubdownall'))+'</span></button>';
  /* The chapter filter (Todo / Cap. 1 / Cap. 2) applies only to refractions — ultimatums and
     boons are shared by both chapters — so it lives inside the refractions panel now, not here. */
  /* Frame skin: v1 (5argon's clean frame) or v2 (textured). Same art and text, different frame. */
  h+='<div class="tla-ub-view tla-ub-skin" role="group" aria-label="'+esc(t('ubframe'))+'">';
  h+='<button type="button" class="tla-ub-viewbtn'+(ubSkin==='v1'?' is-on':'')+'" data-ubskin="v1" aria-pressed="'+(ubSkin==='v1')+'" aria-label="'+esc(t('ubframev1'))+'"><span>V1</span></button>';
  h+='<button type="button" class="tla-ub-viewbtn'+(ubSkin==='v2'?' is-on':'')+'" data-ubskin="v2" aria-pressed="'+(ubSkin==='v2')+'" aria-label="'+esc(t('ubframev2'))+'"><span>V2</span></button>';
  h+='</div>';
  /* View toggle: the classic list (with one large card) or a gallery of every card. */
  h+='<div class="tla-ub-view" role="group" aria-label="'+esc(t('ubviewlabel'))+'">';
  h+='<button type="button" class="tla-ub-viewbtn'+(ubView==='list'?' is-on':'')+'" data-ubview="list" aria-pressed="'+(ubView==='list')+'" aria-label="'+esc(t('ubviewlist'))+'">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>'
    +'<span>'+esc(t('ubviewlist'))+'</span></button>';
  h+='<button type="button" class="tla-ub-viewbtn'+(ubView==='gallery'?' is-on':'')+'" data-ubview="gallery" aria-pressed="'+(ubView==='gallery')+'" aria-label="'+esc(t('ubviewgallery'))+'">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>'
    +'<span>'+esc(t('ubviewgallery'))+'</span></button>';
  h+='</div>';
  h+='</div>';
  h+='<div class="tla-ub-tabs" role="tablist" aria-label="'+esc(t('ubtablabel'))+'">';
  UB_TABS.forEach(function(cat){
    var on=cat===ubTab, items=ubItems(s,cat);
    h+='<button type="button" role="tab" class="tla-ub-tab'+(on?' is-on':'')+'" id="ubtab-'+cat
      +'" data-ubtab="'+cat+'" aria-selected="'+(on?'true':'false')+'" aria-controls="ubpanel-'+cat
      +'" tabindex="'+(on?'0':'-1')+'">'+esc(ubLabel(cat))
      +(items.length?' <span class="tla-ub-n">'+items.length+'</span>':'')+'</button>';
  });
  h+='</div>';
  UB_TABS.forEach(function(cat){
    var on=cat===ubTab, items=ubItems(s,cat);
    h+='<div class="tla-ub-panel" id="ubpanel-'+cat+'" role="tabpanel" aria-labelledby="ubtab-'+cat+'"'
      +(on?'':' hidden')+'>';
    /* Refractions carry the chapter + campaign/scenario filters, above their content. */
    if(cat==='refraction')h+=ubRefracFilterBar(s);
    if(!items.length){
      h+='<div class="tla-soon"><p class="tla-soon-h">'+esc(t('soon'))+'</p>'
        +'<p class="tla-soon-d">'+esc(t(cat==='refraction'&&(ubCampaign||ubScenario)?'ubreffilternone':'ubrefsoon'))+'</p></div>';
    }else if(ubView==='gallery'){
      /* Gallery: every card in the tab (like 5argon's page), using the full width;
         a card enlarges to a full-size render in the lightbox on click. */
      h+='<div class="tla-ub-gallery">';
      items.forEach(function(it){
        h+='<div class="tla-ub-gcard'+(it.pending?' is-pending':'')+'" data-slug="'+esc(it.slug)+'">'
          +ubChapChip(it)+ubDetailHTML(it)+'</div>';
      });
      h+='</div>';
    }else{
      /* List: a scrollable list of names + thumbnails (big, 5argon-style) beside one
         large live card. Picking a name swaps the card. */
      var sel=ubChosen(s,cat);
      h+='<div class="tla-ub-main"><ul class="tla-ub-list" role="listbox" aria-label="'+esc(ubLabel(cat))+'">';
      items.forEach(function(it){
        var o=it.slug===sel;
        var sub='';
        var rp=it.refraction?ubRefractionParts(it):null;
        if(rp){
          /* Two lines: the campaign, then (if this refraction is scenario-specific) the
             scenario — each labelled and shown with its symbol where known, like 5argon's list. */
          sub='<span class="tla-ub-isub tla-ub-isub2"'+(it.pending?' lang="en"':'')+'>'
            +'<span class="tla-ub-isubrow"><span class="tla-ub-isublbl">'+esc(t('refrcampaign'))+':</span>'+(rp.collIcon?ubSymHTML(rp.collIcon):'')+'<span>'+esc(rp.campaign)+'</span></span>';
          if(rp.hasScenario)sub+='<span class="tla-ub-isubrow"><span class="tla-ub-isublbl">'+esc(t('refrscenario'))+':</span>'+(rp.setIcon?ubSymHTML(rp.setIcon):'')+'<span>'+esc(rp.scenario)+'</span></span>';
          sub+='</span>';
        }else if(it.subtitle&&it.subtitle.length){
          sub='<span class="tla-ub-isub"'+(it.pending?' lang="en"':'')+'>'
            +(it.set?ubSymHTML(it.set):'')+'<span>'+runsHTML(it.subtitle,true)+'</span></span>';
        }
        var chip=ubChapChip(it);
        h+='<li role="option" class="tla-ub-item'+(o?' is-sel':'')+(it.pending?' is-pending':'')+'" id="ubopt-'+esc(it.slug)
          +'" data-ubitem="'+esc(it.slug)+'" aria-selected="'+(o?'true':'false')+'" tabindex="'+(o?'0':'-1')+'">'
          +'<img class="tla-ub-thumb" src="assets/'+esc(ubThumbSrc(it))+'" width="'+it.tw+'" height="'+it.th
          +'" loading="lazy" alt=""><span class="tla-ub-iwrap"><span class="tla-ub-iname"'+(it.pending?' lang="en"':'')+'>'+esc(it.name)+'</span>'+sub+'</span>'
          +chip+(it.pending?'<span class="tla-ub-en" title="'+esc(t('ubpending'))+'">EN</span>':'')+'</li>';
      });
      h+='</ul><div class="tla-ub-detail">'+ubPaneHTML(s,cat,sel)+'</div></div>';
    }
    h+='</div>';
  });
  h+='</div>';
  /* Credit, with the source linked: the cards are community-made, not official. */
  h+='<p class="tla-ub-credit">'+esc(t('ubcredit'))+' '
    +'<a class="tla-extlink" href="https://arkham-starter.com/ultimatums-and-boons" target="_blank" rel="noopener">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg>'
    +esc(t('ubcreditlink'))+'</a></p>';
  return h;
}
/* Re-render only the viewer in place, keeping the reader's scroll position — a full render()
   rebuilds the whole chapter and resets the scroll to the top, which made every filter click jump
   the page. Replacing just the `.tla-ub` block avoids both the jump and the flash. */
function ubReRender(){
  if(!curSec)return;
  var old=elMain.querySelector('.tla-ub');
  if(!old){render(curSec.id,null,false); return;}
  var top=elMain.scrollTop;
  var tmp=document.createElement('div');
  tmp.innerHTML=ubHTML(curSec);
  var neo=tmp.querySelector('.tla-ub');
  if(neo){old.parentNode.replaceChild(neo, old); bindUB();}
  elMain.scrollTop=top;
}
/* Switch view mode (list / gallery), keeping tab + selection + scroll. */
function ubSetView(v){
  if((v!=='list'&&v!=='gallery')||v===ubView)return;
  ubView=v; try{localStorage.setItem('tla-ubview',v);}catch(e){}
  ubReRender();
}
/* Switch the frame skin (v1 / v2): every picture and thumbnail swaps folder, so re-render. */
function ubSetSkin(v){
  if((v!=='v1'&&v!=='v2')||v===ubSkin)return;
  ubSkin=v; try{localStorage.setItem('tla-ubskin',v);}catch(e){}
  ubReRender();
}
/* Switch chapter filter (all / cap1 / cap2) — counts and every panel change. The campaign/
   scenario filter is cleared with it: those live in a chapter, so a stale pick could point at
   nothing under the new chapter. */
function ubSetChap(v){
  if((v!=='all'&&v!=='cap1'&&v!=='cap2')||v===ubChap)return;
  ubChap=v; ubCampaign=''; ubScenario='';
  try{localStorage.setItem('tla-ubchap',v);}catch(e){}
  ubReRender();
}
/* Pick a campaign to filter the refractions by: this also drops any scenario pick and forces the
   chapter filter to 'all', so the two filters never hide each other. */
function ubSetCampaign(v){
  ubCampaign=v||''; ubScenario='';
  if(ubCampaign)ubChap='all';
  ubReRender();
}
function ubSetScenario(v){
  ubScenario=v||'';
  ubReRender();
}
/* Switch the ultimatum/boon cut of the refractions. */
function ubSetType(v){
  if((v!=='all'&&v!=='ultimatum'&&v!=='boon')||v===ubType)return;
  ubType=v; try{localStorage.setItem('tla-ubtype',v);}catch(e){}
  ubReRender();
}
/* Reset the refractions filter to its default: every chapter, both types, no campaign. */
function ubClearFilter(){
  ubCampaign=''; ubScenario=''; ubChap='all'; ubType='all';
  try{localStorage.setItem('tla-ubchap','all'); localStorage.setItem('tla-ubtype','all');}catch(e){}
  ubReRender();
}
function ubSelectTab(root,cat){
  ubTab=cat;
  [].forEach.call(root.querySelectorAll('.tla-ub-tab'),function(b){
    var on=b.getAttribute('data-ubtab')===cat;
    b.classList.toggle('is-on',on); b.setAttribute('aria-selected',on?'true':'false'); b.tabIndex=on?0:-1;
  });
  [].forEach.call(root.querySelectorAll('.tla-ub-panel'),function(p){
    p.hidden=p.id!=='ubpanel-'+cat;
  });
  ubFitVisible(root);
}
function ubSelectItem(li){
  var list=li.closest('.tla-ub-list'), main=li.closest('.tla-ub-main'), s=curSec;
  var cat=li.closest('.tla-ub-panel').id.replace('ubpanel-','');
  var slug=li.getAttribute('data-ubitem');
  ubSel[cat]=slug;
  [].forEach.call(list.querySelectorAll('.tla-ub-item'),function(x){
    var on=x===li; x.classList.toggle('is-sel',on); x.setAttribute('aria-selected',on?'true':'false'); x.tabIndex=on?0:-1;
  });
  var det=main.querySelector('.tla-ub-detail'), it=ubFindItem(s,cat,slug);
  if(det&&it){det.innerHTML=ubPaneHTML(s,cat,slug); ubFitCard(det.querySelector('.tla-ubc'));}
}
/* Move `d` cards along the shown list. Goes through ubSelectItem so the list, the card and the
   stepper stay one thing; then puts focus back on the arrow that was clicked — or, when that
   arrow has just become the end of the stack and disabled itself, on the other one, so keyboard
   focus is never dropped on the floor mid-way through the deck. */
function ubStep(root,d){
  var s=curSec, cat=ubTab, a=ubItems(s,cat), i=ubIndexOf(s,cat,ubChosen(s,cat)), j=i+d;
  if(i<0||j<0||j>=a.length)return;
  var li=root.querySelector('#ubpanel-'+cat+' [data-ubitem="'+cssEsc(a[j].slug)+'"]');
  if(!li)return;
  ubSelectItem(li);
  if(li.scrollIntoView)li.scrollIntoView({block:'nearest'});
  var pane=root.querySelector('#ubpanel-'+cat+' .tla-ub-detail');
  var want=pane&&pane.querySelector('[data-ubstep="'+d+'"]:not([disabled])');
  if(!want&&pane)want=pane.querySelector('[data-ubstep]:not([disabled])');
  if(want)want.focus();
}
function ubTabKeys(e,root){
  var tab=e.target.closest('.tla-ub-tab'); if(!tab)return;
  var tabs=[].slice.call(root.querySelectorAll('.tla-ub-tab'));
  var i=tabs.indexOf(tab),n=tabs.length,j=-1;
  if(e.key==='ArrowRight'||e.key==='ArrowDown')j=(i+1)%n;
  else if(e.key==='ArrowLeft'||e.key==='ArrowUp')j=(i-1+n)%n;
  else if(e.key==='Home')j=0; else if(e.key==='End')j=n-1;
  if(j<0)return;
  e.preventDefault(); ubSelectTab(root,tabs[j].getAttribute('data-ubtab')); tabs[j].focus();
}
function ubListKeys(e,li){
  var items=[].slice.call(li.closest('.tla-ub-list').querySelectorAll('.tla-ub-item'));
  var i=items.indexOf(li),n=items.length,j=-1;
  if(e.key==='ArrowDown')j=(i+1)%n; else if(e.key==='ArrowUp')j=(i-1+n)%n;
  else if(e.key==='Home')j=0; else if(e.key==='End')j=n-1;
  else if(e.key==='Enter'||e.key===' '){e.preventDefault(); ubSelectItem(li); return;}
  if(j<0)return;
  e.preventDefault(); ubSelectItem(items[j]); items[j].focus();
}
function bindUB(){
  var root=elMain.querySelector('.tla-ub'); if(!root)return;
  root.addEventListener('click',function(e){
    var dl=e.target.closest('.tla-ubc-dl'); if(dl){ubDownload(dl.closest('.tla-ubc')); return;}
    if(e.target.closest('#ubdraw-open')){openDraw(); return;}
    var da=e.target.closest('#ubdownall'); if(da){ bleedModal(UB_TRIM_MM,ubBleed,function(bleed){ubBleed=bleed; ubDownloadAll(da);}); return;}
    var sb2=e.target.closest('[data-ubskin]'); if(sb2){ubSetSkin(sb2.getAttribute('data-ubskin')); return;}
    var vb=e.target.closest('.tla-ub-viewbtn'); if(vb){ubSetView(vb.getAttribute('data-ubview')); return;}
    var cb=e.target.closest('[data-ubchap]'); if(cb){ubSetChap(cb.getAttribute('data-ubchap')); return;}
    var tb=e.target.closest('[data-ubtype]'); if(tb){ubSetType(tb.getAttribute('data-ubtype')); return;}
    var sb=e.target.closest('[data-ubstep]'); if(sb){ubStep(root,parseInt(sb.getAttribute('data-ubstep'),10)); return;}
    var clr=e.target.closest('[data-ubclear]'); if(clr){ubClearFilter(); return;}
    var tab=e.target.closest('.tla-ub-tab'); if(tab){ubSelectTab(root,tab.getAttribute('data-ubtab')); tab.focus(); return;}
    // gallery mode: a card (anywhere but its download button) enlarges in the lightbox
    var gc=e.target.closest('.tla-ub-gcard .tla-ubc'); if(gc){ubZoomCard(gc); return;}
    // list mode: a name swaps the shown card
    var li=e.target.closest('.tla-ub-item'); if(li){ubSelectItem(li); li.focus();}
  });
  root.addEventListener('change',function(e){
    var camp=e.target.closest('[data-ubcamp]'); if(camp){ubSetCampaign(camp.value); return;}
    var scen=e.target.closest('[data-ubscen]'); if(scen){ubSetScenario(scen.value); return;}
  });
  root.addEventListener('keydown',function(e){
    if(e.target.closest('.tla-ub-tab')){ubTabKeys(e,root); return;}
    var li=e.target.closest('.tla-ub-item'); if(li)ubListKeys(e,li);
  });
  ubFitVisible(root);
  /* The card fonts load lazily; their real metrics differ from the fallback, so the
     rule is re-fitted once they are ready. */
  if(window.document&&document.fonts&&document.fonts.ready){
    document.fonts.ready.then(function(){ubFitVisible(root);}).catch(function(){});
  }
}

/* ArkhamDB is per-language on subdomains (es.arkhamdb.com, fr…); English is the bare
   domain. The card id already carries the pack + padded number (e.g. 12020). */
function adbCardUrl(id){
  var sub=(lang&&lang!=='en')?lang+'.':'';
  return 'https://'+sub+'arkhamdb.com/card/'+encodeURIComponent(id);
}
/* A card search on ArkhamDB in the reader's language — lists every printing of the name
   and its forum, so it needs no exact card id or version. */
function adbSearchUrl(q){
  var sub=(lang&&lang!=='en')?lang+'.':'';
  return 'https://'+sub+'arkhamdb.com/find?q='+encodeURIComponent(q);
}
function prodIcon(art){
  return art?'<span class="tla-prodicon" aria-hidden="true" style="-webkit-mask-image:url(assets/products/'
    +esc(art)+'.svg);mask-image:url(assets/products/'+esc(art)+'.svg)"></span>':'';
}
function adbLink(id){
  return '<a class="tla-adb" href="'+esc(adbCardUrl(id))+'" target="_blank" rel="noopener">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg>'
    +esc(t('viewadb'))+'</a>';
}
/* ---- the interactive Taboo list (Resources), built from ArkhamDB by tools/taboos.py ---- */
/* ArkhamDB writes the taboo mutation text with its own icon tokens ([reaction], [willpower]…)
   and light HTML. Convert the tokens to the site's game icons, keep bold/italic, and escape
   everything else — so nothing but <strong>/<em>/icons is emitted from that external text. */
function adbTokenIcon(tok){
  var map={action:'action',reaction:'reaction',fast:'fast',free:'fast',lightning:'fast',
    willpower:'willpower',intellect:'intellect',combat:'combat',agility:'agility',wild:'wild',
    skull:'skull',cultist:'cultist',tablet:'tablet',elder_thing:'elderthing',elderthing:'elderthing',
    auto_fail:'autofail',elder_sign:'eldersign',bless:'bless',curse:'curse',frost:'frost',
    per_investigator:'perinvestigator',guardian:'guardian',seeker:'seeker',rogue:'rogue',
    mystic:'mystic',survivor:'survivor'};
  return map[tok]||null;
}
function adbText(html){
  if(!html)return '';
  // Drop every HTML tag (ArkhamDB's text is light HTML), then split out its icon tokens
  // ([reaction], [willpower]…): text is escaped and a known token becomes a game icon, so
  // nothing but game icons and escaped text is ever emitted from this external string.
  var s=String(html).replace(/<[^>]*>/g,'');
  var parts=s.split(/(\[[a-z_]+\])/i), out='';
  for(var i=0;i<parts.length;i++){
    var pp=parts[i]; if(!pp)continue;
    var m=pp.match(/^\[([a-z_]+)\]$/i);
    if(m){var ic=adbTokenIcon(m[1].toLowerCase()); out+=ic?iconHTML(ic):esc(pp);}
    else out+=esc(pp);
  }
  return out;
}
/* A per-card index of the current taboo list, above the chapter's own full text: every card as a
   direct link to ArkhamDB (in the reader's language), with its product icon and collection number
   and its bucket (Chained/Mutated/Forbidden). The mutation text itself is the chapter's prose
   below — official and in the reader's language — so it is not repeated here. */
function taboosHTML(s){
  var tb=s.taboos; if(!tb)return '';
  /* Closed by default: the chapter's own prose is what a reader came for, and ninety cards
     between the heading and the first paragraph buries it. The summary says what is inside. */
  var h='<details class="tla-taboos">';
  h+='<summary class="tla-taboos-sum"><span class="tla-taboos-sumt">'+esc(t('tabooindex'))+'</span>'
    +'<span class="tla-taboo-ver">'+esc(t('tabooversion').replace('{d}',fmtDate(tb.date)))+'</span></summary>';
  h+='<div class="tla-taboos-body">';
  /* What the list IS, before ninety card names. Written and translated into every language
     long ago; it simply had never been rendered. */
  h+='<p class="tla-taboos-lead">'+esc(t('taboolead'))+'</p>';
  (tb.groups||[]).forEach(function(g){
    /* h2: these bucket headings sit under the chapter's h1, at the same level as its entries —
       an h3 here would skip a level (the taboo index renders before those entries). */
    h+='<section class="tla-taboo-grp"><h2 class="tla-taboo-h">'+esc(t('taboocat_'+g.cat))
      +' <span class="tla-taboo-n">'+g.cards.length+'</span></h2>';
    /* …and what the bucket MEANS. "Chained" says nothing on its own to a reader who has not
       met the taboo list before, and the one-line answer was already written per language. */
    h+='<p class="tla-taboo-desc">'+esc(t('taboodesc_'+g.cat))+'</p>';
    h+='<ul class="tla-taboo-list">';
    g.cards.forEach(function(c){
      h+='<li class="tla-taboo-card is-'+esc(g.cat)+'">';
      h+='<a class="tla-taboo-name" href="'+esc(adbCardUrl(c.code))+'" target="_blank" rel="noopener">'+esc(c.name)
        +'<svg class="tla-taboo-ext" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg></a>';
      h+='<span class="tla-taboo-coll">'+(c.art?prodIcon(c.art):'')
        +(c.packName?'<span class="tla-taboo-pack">'+esc(c.packName)+'</span>':'')
        +(c.position?'<span class="tla-taboo-pos">'+esc(String(c.position))+'</span>':'')+'</span>';
      if(g.cat==='chained')h+='<span class="tla-taboo-tag tla-taboo-xp">'+esc((c.xp>0?'+':'')+c.xp+' '+t('tabooxp'))+'</span>';
      else if(g.cat==='forbidden')h+='<span class="tla-taboo-tag tla-taboo-forb">'+esc(t('taboocat_forbidden'))+'</span>';
      /* What the mutation actually says. Everything else on this row is in the reader's
         language — the card, its product, the category — but ArkhamDB keeps the mutation
         wording in English only, so it is tagged lang="en" and labelled as such: a screen
         reader switches voice for it, and a reader can see why it is the odd one out. The
         FAQ's own taboo chapter, linked below the list, has it translated. */
      if(c.text)h+='<p class="tla-taboo-mut" lang="en">'
        +'<span class="tla-taboo-mutlbl">'+esc(t('taboomut'))+'</span>'+adbText(c.text)+'</p>';
      h+='</li>';
    });
    h+='</ul></section>';
  });
  /* Deliberately NO "see the FAQ's taboo chapter" link, though two translated strings for one
     exist in the packs' history: attachTaboos() hangs this index on the section keyed
     'faq-taboos', which IS that chapter. The reader is already on it and its prose is directly
     below, so the link would point at the page it is printed on. */
  h+='<p class="tla-taboo-src"><a class="tla-extlink" href="'+esc(tb.source||'https://arkhamdb.com/rules')+'" target="_blank" rel="noopener">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg>'
    +esc(t('taboosource'))+'</a></p>';
  h+='</div></details>';
  return h;
}
/* The Modified Reprints chapter as a table: set symbol, collection number, card name,
   and a link to the card on ArkhamDB in the reader's language. */
function reprintsHTML(s){
  var rows=s.reprints||[]; if(!rows.length)return '';
  var icon=s.reprintsIcon;
  var h='<div class="tla-rp-wrap"><table class="tla-reprints"><thead><tr>'
    +'<th class="tla-rp-set"><span class="tla-sr">'+esc(t('reprintset'))+'</span></th>'
    +'<th class="tla-rp-num">'+esc(t('reprintnum'))+'</th>'
    +'<th class="tla-rp-card">'+esc(t('reprintcard'))+'</th>'
    +'<th class="tla-rp-link"><span class="tla-sr">ArkhamDB</span></th></tr></thead><tbody>';
  rows.forEach(function(r){
    h+='<tr><td class="tla-rp-set">'+prodIcon(icon)+'</td>'
      +'<td class="tla-rp-num">'+esc(r.num)+'</td>'
      +'<td class="tla-rp-card">'+esc(r.name)+'</td>'
      +'<td class="tla-rp-link">'+adbLink(r.adb)+'</td></tr>';
  });
  return h+'</tbody></table></div>';
}

/* ---- the community's deeper timing diagram (tools/fanmade.py) ----
   A chapter the community has documented far past the book: the same procedure, broken into
   every triggering point with the cards that fire there. It is NOT official, which is the first
   thing said about it and the reason it is a separate cut of the chapter rather than mixed into
   the book's own text. Rendered as a real table — three columns, a row per step — because that
   is what it is; a screenshot of one would be unreadable, unsearchable and untranslatable. */
var FM_MAIL='rinconmiskatonic@gmail.com';
/* The Spanish source prints the elder-sign mark as a glyph in the middle of a sentence; the
   transcription keeps it as ✷, and here it becomes the site's own icon, named like every other. */
function fmText(str){
  var parts=String(str||'').split('✷');
  var h=esc(parts[0]);
  for(var i=1;i<parts.length;i++)h+=iconHTML('eldersign')+esc(parts[i]);
  return h;
}
function fmCellHTML(order){
  if(!order||!order.length)return '';
  var h='';
  order.forEach(function(o){
    if(o.type==='head')h+='<p class="tla-fm-h">'+fmText(o.t)+'</p>';
    else if(o.type==='eg')h+='<p class="tla-fm-eg"><span class="tla-sr">'+esc(t('fmeg'))+': </span>'+fmText(o.t)+'</p>';
    else h+='<p class="tla-fm-p">'+fmText(o.t)+'</p>';
  });
  return h;
}
/* A translated sentence with a "{mail}" placeholder in it, as HTML with the address linked.
   The placeholder is what lets a translator put the address where their language wants it. */
function mailSplitHTML(str){
  var p=String(str||'').split('{mail}');
  if(p.length<2)return esc(p[0]||'');
  return esc(p[0])+'<a href="mailto:'+FM_MAIL+'">'+esc(FM_MAIL)+'</a>'+esc(p[1]||'');
}
function fanmadeHTML(s){
  var fm=s.fanmade; if(!fm)return '';
  var warn=t('fmwarn').split('{mail}');
  /* Not aria-labelledby here: that would make this a landmark named by the same heading as the
     scrollable table region inside it, and two landmarks with one name are indistinguishable in
     a landmarks list. The h2 heads the part; the region below carries the name. */
  /* A block this language has no transcription of is shown in the language it exists in.
     Tagged lang=… so a screen reader reads it in that voice instead of mispronouncing it in
     the reader's own, exactly as the ultimatum cards do for their English fallback. */
  var L=fm.lang?' lang="'+esc(fm.lang)+'"':'';
  var h='<section class="tla-fm"'+L+'>';
  h+='<h2 class="tla-fm-title" id="fm-h"'+L+'>'+esc(fm.title||t('fmtitle'))+'</h2>';
  /* Same loud callout the site uses for the obsolete environments: this is the one thing a
     reader must take in before reading a line of it. */
  h+='<aside class="tla-obsolete" role="note">'
    +'<div class="tla-obsolete-tag">'+esc(t('noticeword'))+'</div>'
    +'<div class="tla-obsolete-body"><p class="tla-obsolete-lead">'+esc(warn[0])
    +'<a href="mailto:'+FM_MAIL+'">'+esc(FM_MAIL)+'</a>'+esc(warn[1]||'')+'</p>'
    /* …and, when the table is not in the reader's language, why — and how to change that. In
       the reader's OWN language: a notice nobody can read is not a notice. */
    +(fm.lang?'<p class="tla-obsolete-lead">'+mailSplitHTML(t('fmnottranslated'))+'</p>':'')
    +'</div></aside>';
  (fm.lead||[]).forEach(function(l){
    h+='<p class="tla-p">'+(l.h?'<strong>'+esc(l.h)+':</strong> ':'')+fmText(l.t)+'</p>';
  });
  /* The table is wider than a phone, so it scrolls in its own box — which then has to be
     reachable by keyboard, and named, or a keyboard user can never scroll it. */
  h+='<div class="tla-fm-wrap" tabindex="0" role="region" aria-labelledby="fm-h">'
    +'<table class="tla-fm-table"><thead><tr>'
    +'<th scope="col">'+esc(t('fmstep'))+'</th><th scope="col">'+esc(t('fmdesc'))+'</th>'
    +'<th scope="col">'+esc(t('fmorder'))+'</th></tr></thead><tbody>';
  (fm.steps||[]).forEach(function(st){
    var win=st.kind==='window';
    /* A player-window row is not a numbered step: it has no id, so rather than leave an empty
       header cell it makes its own label the row's header, across both columns. That label is
       the interface's own words, not the source's shouted caps — which a screen reader would
       spell out letter by letter. */
    h+='<tr'+(win?' class="is-window"':'')+'>';
    if(win)h+='<th scope="row" colspan="2" class="tla-fm-win">'+esc(t('fmwindow'))+'</th>';
    else h+='<th scope="row" class="tla-fm-id">'+esc(st.id||'')+'</th>'
      +'<td class="tla-fm-desc">'+fmText(st.desc)+'</td>';
    h+='<td class="tla-fm-order">'+fmCellHTML(st.order)+'</td></tr>';
  });
  h+='</tbody></table></div>';
  var cr=fm.credit||{}, or=fm.original||{};
  if(cr.author)h+='<p class="tla-fm-credit">'+esc(t('fmcredit').replace('{author}',cr.author))
    +(cr.updated?' '+esc(t('fmupdated').replace('{date}',fmtDate(cr.updated))):'')+'</p>';
  /* The work every version of this table descends from, credited on all of them. Separate from
     the line above, which credits whoever transcribed or translated it — a different debt. */
  if(or.author){
    var op=t('fmoriginal').split('{author}');
    h+='<p class="tla-fm-credit">'+esc(op[0]||'')
      +(or.url?'<a href="'+esc(or.url)+'" rel="noopener noreferrer" target="_blank">'
        +esc(or.author)+'</a>':esc(or.author))
      +esc(op[1]||'')+'</p>';
  }
  return h+'</section>';
}

/* The Grimoire's living definition of the environments (in the optional rules), for the FAQ's
   obsolete-Beta warning to link to. Found by the shared section key, then its environments
   subhead, so it lands right in every language; falls back to the section, then null. */
function grimoireEnvTarget(){
  var opt=(data.sections||[]).filter(function(x){return x.key==='optional-rules';})[0];
  if(!opt)return null;
  var e=(opt.entries||[]).filter(function(en){return en.role==='subhead'&&/entorno|environment/i.test(en.title||'');})[0];
  return e?e.id:opt.id;
}
/* Said on every chapter of a language whose rulebooks do not exist in it. The chapter's own
   title stays in the language it was borrowed from, which is the honest thing: it IS that
   language's chapter, and naming it is how the reader finds it again over there. */
function nobookHTML(s){
  var to=s.nobook, reg=regOf(to), name=reg?reg.name:to;
  return '<aside class="tla-obsolete" role="note">'
    +'<div class="tla-obsolete-tag">'+esc(t('noticeword'))+'</div>'
    +'<div class="tla-obsolete-body"><p class="tla-obsolete-lead">'+esc(t('secnobook'))+'</p>'
    +'<a class="tla-obsolete-go" href="#'+esc(to)+'/'+esc(s.id)+'" lang="'+esc(to)+'">'
    +esc(t('secnobooklink'))+' <span aria-hidden="true">→</span></a>'
    +'<span class="tla-sr"> ('+esc(name)+')</span>'
    +'</div></aside>';
}
/* ---------- Taboo card viewer (Resources section) ----------
   The reserved "taboos" section becomes this once its card reprints load. Each card is shown as
   FFG prints it and as the taboo list changes it, with the change written under the pair; the two
   card faces are drawn by js/taboo.js (the same renderer as the prototype), everything around them
   is the site's own chrome. Cards a language does not have of its own are shown in English behind
   a beta notice. */
var tabFilter={type:'',cls:'',cat:'',q:''};
var tabBleed=false;   // download with a print bleed margin, toggled in the tools bar
var TAB_CLASSES=['guardian','seeker','rogue','mystic','survivor','neutral'];
/* The taboo-list versions, newest first. Today there is just one — the list FFG published with
   FAQ 2.5 on 2026-02-19. When a new FAQ ships a new list, add an entry here (newest first) and tag
   those cards with a matching `faqv` in the data; the selector, the default and the per-version
   filter then work with no further wiring. `v` is the FAQ number, `date` its publication (ISO). */
var TAB_VERSIONS=[{id:'faq25', v:'2.5', date:'2026-02-19'}];
var tabVersion=TAB_VERSIONS[0].id;   // shown by default: the newest list
/* "<date> (FAQ <v>)" — the date in the reader's own format, the rest a version id, not translated. */
function tabVerLabel(ver){ return fmtDate(ver.date)+' (FAQ '+ver.v+')'; }
function tabCat(c){
  if(c.cat)return c.cat;
  var tb=c.taboo||{};
  if(tb.deck_limit===0)return 'forbidden';
  if(typeof tb.xp==='number'&&!tb.text)return 'chained';
  return 'mutated';
}
function tabFold(s){return String(s||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();}
function tabMatch(c){
  var q=tabFold(tabFilter.q).trim();
  if(q&&tabFold(c.name+' '+(c.subname||'')).indexOf(q)<0)return false;
  if(tabFilter.type&&c.type!==tabFilter.type)return false;
  if(tabFilter.cls&&c.faction!==tabFilter.cls&&c.faction2!==tabFilter.cls&&c.faction3!==tabFilter.cls)return false;
  if(tabFilter.cat&&tabCat(c)!==tabFilter.cat)return false;
  return true;
}
/* The category chip and, on a chained/unchained card, its experience swing. */
function tabCatChip(c){
  var cat=tabCat(c), tb=c.taboo||{};
  var lbl=t('tbcat_'+cat);
  if(cat==='chained'&&typeof tb.xp==='number')lbl+=' ('+(tb.xp>0?'+':'')+tb.xp+' XP)';
  return lbl;
}
/* The change the list makes, in FFG's own words, with the card's symbols — then the note that
   says which face the site assembled and, on a rebuilt face outside English, Fernando's
   disclaimer. `beta` means the cards are the English fallback, so no per-card disclaimer (the
   section-wide beta banner has already said the cards are English). */
function tabChangeHTML(c,beta){
  var cat=tabCat(c), tb=c.taboo||{};
  var body=c.change?TabooCard.runs(c.change)
    :tb.text?TabooCard.runs(tb.text)
    :cat==='forbidden'?esc(t('tbforbiddenrule')):'';
  var out='<span class="tla-tb-cat">'+esc(tabCatChip(c))+'</span> · '+body;
  var cardLang=beta?'en':lang;
  if(cardLang!=='en'){
    if(c.frontSame)out+='<span class="tla-tb-why">'+esc(t('tbfrontsame'))+'</span>';
    else if(cat==='mutated')out+='<span class="tla-tb-why is-warn">'+esc(t('tbdisclaimer'))+'</span>';
    else out+='<span class="tla-tb-why">'+esc(t('tbnoteline'))+'</span>';
  }
  return out;
}
/* One card: its two faces side by side, the change under them, and an investigator's back below
   that when the card has one (for Lola and Mandy the taboo change is ON the back). */
function tabItemHTML(c,beta){
  var ico=function(cls,data,label,path){return '<button type="button" class="'+cls+'" '+data
    +' aria-label="'+esc(label)+'" title="'+esc(label)+'"><svg viewBox="0 0 24 24" fill="none" '
    +'stroke="currentColor" stroke-width="2" aria-hidden="true">'+path+'</svg></button>';};
  /* Corner buttons. The DOWNLOAD lives only on the taboo face — the printed face is for
     comparison, not for saving (it grabs the taboo card and its back). The magnifier zooms and
     is on both. */
  var zoomBtn=ico('tla-tb-zoom','data-tabzoom',t('tbzoom'),'<circle cx="10.5" cy="10.5" r="7"/><path d="M21 21l-5-5"/><path d="M10.5 7.5v6M7.5 10.5h6"/>');
  var dlBtn=ico('tla-tb-dl','data-tabdl',t('ubdownload'),'<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/>');
  var toolsPrinted='<div class="tla-tb-btns">'+zoomBtn+'</div>';
  var toolsTaboo='<div class="tla-tb-btns">'+dlBtn+zoomBtn+'</div>';
  /* One prominent header per card: the name links to ArkhamDB (its own per-language subdomain), then
     the collection number and the card type -- "A la calle · 11055 · Evento". */
  /* The name is an h2 (the card is a section under the page's h1): the plate renders its own name as
     an h3, so without this the heading order jumped h1->h3. The link keeps its class so it stays gold. */
  var head='<div class="tla-tb-head">'
    +'<h2 class="tla-tb-name-h"><a class="tla-tb-name" href="'+esc(adbCardUrl(c.code))+'" target="_blank" rel="noopener">'+esc(c.name)+'</a></h2>'
    +(c.subname?'<span class="tla-tb-sub">'+esc(c.subname)+'</span>':'')
    +'<span class="tla-tb-code">'+esc(c.code)+'</span>'
    +(c.typeName?'<span class="tla-tb-type">'+esc(c.typeName)+'</span>':'')+'</div>';
  var faceCap=function(label){return '<figcaption class="tla-tb-cap"><span class="tla-tb-badge">'
    +esc(label)+'</span></figcaption>';};
  var h='<div class="tla-tb-item" data-code="'+esc(c.code)+'"'
    +' data-type="'+esc(c.type)+'"'
    +' data-factions="'+esc([c.faction,c.faction2,c.faction3].filter(Boolean).join(' '))+'"'
    +' data-cat="'+esc(tabCat(c))+'"'
    +' data-faqv="'+esc(c.faqv||TAB_VERSIONS[0].id)+'"'   /* which taboo-list version this card is on */
    +(c.backChange?' data-backmod':'')          /* Lola, Mandy: the deck-building back is tabooed too */
    +(c.frontSame?' data-frontsame':'')          /* Mandy: only her back changed, front is unchanged */
    +' data-name="'+esc(tabFold(c.name+' '+(c.subname||'')))+'">';
  h+=head;
  var inv=(c.type==='investigator');
  /* An investigator is two-sided, so its card splits into a FRONT (Delantera) and a BACK (Trasera)
     section, each headed and ruled off. The others are a single row. */
  if(inv)h+='<div class="tla-tb-sidehead">'+esc(t('tbfront'))+'</div>';
  /* Three columns: the printed card on the left, the taboo card in the centre, the change and its
     notes on the right. Each face is clickable to zoom. */
  h+='<div class="tla-tb-row">';
  /* The face is click-to-zoom for the mouse (cursor:zoom-in); keyboard users reach the same zoom
     through the always-visible magnifier button, so the face itself is not a tab stop — that keeps
     one clean, named control per action instead of an unnamed focusable wrapping two buttons. */
  h+='<figure class="tla-tb-face" data-face="printed">'+faceCap(t('tbimpresa'))+toolsPrinted+TabooCard.html(c,false)+'</figure>';
  if(c.pdf)h+='<figure class="tla-tb-face" data-face="taboo">'+faceCap(t('tbtaboo'))+toolsTaboo+TabooCard.html(c,true)+'</figure>';
  else h+='<div class="tla-tb-face-empty" aria-hidden="true"></div>';
  h+='<div class="tla-tb-note">'+tabChangeHTML(c,beta)+'</div>';
  h+='</div>';
  /* The back. For an investigator whose deck-building side is ALSO tabooed (Lola, Mandy) we show BOTH
     the printed back and the tabooed back side by side, exactly like the front, so the two can be
     compared. Others show their single, unchanged back. Non-investigators never carry a back. */
  if(inv&&c.back){
    h+='<div class="tla-tb-sidehead">'+esc(t('tbback'))+'</div>';
    h+='<div class="tla-tb-row tla-tb-backrow">';
    if(c.backChange&&c.backTaboo){
      h+='<figure class="tla-tb-face" data-face="back-printed">'+faceCap(t('tbimpresa'))+toolsPrinted+TabooCard.back(c,c.back)+'</figure>';
      h+='<figure class="tla-tb-face" data-face="back-taboo">'+faceCap(t('tbtaboo'))+toolsTaboo+TabooCard.back(c,c.backTaboo)+'</figure>';
    }else{
      h+='<figure class="tla-tb-face" data-face="back">'+faceCap(t('tbback'))+toolsTaboo+TabooCard.back(c,c.back)+'</figure>';
    }
    h+='</div>';
    if(c.backAssisted&&!beta&&lang!=='en')h+='<span class="tla-tb-why is-warn">'+esc(t('tbdisclaimer'))+'</span>';
  }
  h+='</div>';
  return h;
}
function tabooCardsHTML(s){
  var cards=(s.tabooCards||[]).slice().sort(function(a,b){return a.name.localeCompare(b.name,lang);});
  var beta=!!s.tabooBeta;
  var h='';
  /* Cards the reader's language has none of: shown in English, said so in English. */
  if(beta)h+='<aside class="tla-obsolete" role="note"><div class="tla-obsolete-tag">Beta</div>'
    +'<div class="tla-obsolete-body"><p class="tla-obsolete-lead">'+esc(t('tbbeta'))+'</p></div></aside>';
  /* A short lead before the cards: what the taboo list is and a link to the FAQ's full write-up
     (found by the shared 'faq-taboos' key so it resolves to the reader's own language). WHICH list
     this is now lives in the version selector at the top of the sidebar, not in a note here. */
  var faqSec=(data.sections||[]).filter(function(x){return x.key==='faq-taboos';})[0];
  var readmore=faqSec?(' <a class="xref" href="#'+esc(lang)+'/'+esc(faqSec.id)+'" data-t="'+esc(faqSec.id)+'">'+esc(t('tbreadmore'))+'</a>'):'';
  h+='<div class="tla-tb-intro"><p class="tla-tb-intro-lead">'+esc(t('tbintro'))+readmore+'</p></div>';
  /* Which types and classes are actually present, for the filters (counts alongside). */
  var byType={}, byClass={}, byCat={};
  cards.forEach(function(c){
    byType[c.type]=(byType[c.type]||0)+1;
    [c.faction,c.faction2,c.faction3].forEach(function(f){if(f)byClass[f]=(byClass[f]||0)+1;});
    byCat[tabCat(c)]=(byCat[tabCat(c)]||0)+1;
  });
  /* Type labels come from the cards themselves (already translated); class and category from ui. */
  var typeName={}; cards.forEach(function(c){if(c.typeName)typeName[c.type]=c.typeName;});
  var sel=function(id,cur,allLabel,pairs,aria){
    var o='<option value="">'+esc(allLabel)+'</option>';
    pairs.forEach(function(p){o+='<option value="'+esc(p[0])+'"'+(cur===p[0]?' selected':'')+'>'+esc(p[1])+' · '+p[2]+'</option>';});
    return '<select id="tabf-'+id+'" data-tabfilter="'+id+'" aria-label="'+esc(aria)+'">'+o+'</select>';
  };
  var typePairs=Object.keys(byType).map(function(k){return [k,typeName[k]||k,byType[k]];});
  var classPairs=TAB_CLASSES.filter(function(k){return byClass[k];}).map(function(k){return [k,t('tbclass_'+k),byClass[k]];});
  var catPairs=['chained','mutated','forbidden'].filter(function(k){return byCat[k];}).map(function(k){return [k,t('tbcat_'+k),byCat[k]];});
  /* The filters live in a sticky sidebar on the left, so they stay in view down the whole list. */
  h+='<div class="tla-tb-layout">';
  h+='<aside class="tla-tb-side" aria-label="'+esc(t('tbfilters'))+'">'
    +'<div class="tla-tb-field tla-tb-field-ver"><label for="tabf-ver">'+esc(t('tbfaqsel'))+'</label>'
    +'<select id="tabf-ver" data-tabver aria-label="'+esc(t('tbfaqsel'))+'" title="'+esc(tabVerLabel((TAB_VERSIONS.filter(function(x){return x.id===tabVersion;})[0])||TAB_VERSIONS[0]))+'">'
    +TAB_VERSIONS.map(function(ve){return '<option value="'+esc(ve.id)+'"'+(ve.id===tabVersion?' selected':'')+'>'+esc(tabVerLabel(ve))+'</option>';}).join('')
    +'</select></div>'
    +'<div class="tla-tb-field"><label for="tab-q">'+esc(t('tbsearchlabel'))+'</label>'
    +'<input id="tab-q" type="search" data-tabfilter="q" value="'+esc(tabFilter.q)+'" placeholder="'+esc(t('tbsearchph'))+'"></div>'
    +'<div class="tla-tb-field"><label for="tabf-cat">'+esc(t('tbfiltercat'))+'</label>'+sel('cat',tabFilter.cat,t('tball'),catPairs,t('tbfiltercat'))+'</div>'
    +'<div class="tla-tb-field"><label for="tabf-type">'+esc(t('tbfiltertype'))+'</label>'+sel('type',tabFilter.type,t('tball'),typePairs,t('tbfiltertype'))+'</div>'
    +'<div class="tla-tb-field"><label for="tabf-cls">'+esc(t('tbfilterclass'))+'</label>'+sel('cls',tabFilter.cls,t('tball'),classPairs,t('tbfilterclass'))+'</div>'
    +'<button type="button" class="tla-tb-clear" data-tabclear hidden>'+esc(t('tbclear'))+'</button>'
    +'<span class="tla-tb-count" data-tab-count role="status" aria-live="polite">'+cards.length+' / '+cards.length+'</span>'
    +'<div class="tla-tb-side-dl">'
    +'<button type="button" class="tla-tb-btn" data-tabdlall>'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>'
    +'<span class="tla-tb-dlall-label">'+esc(t('ubdownall'))+'</span></button>'
    /* only the shown (filtered) cards download, so warn when a filter is narrowing the set */
    +'<p class="tla-tb-dlnote" data-tab-dlnote hidden>'+esc(t('tbdlnote'))+'</p></div>'
    +'</aside>';
  h+='<div class="tla-tb-main">';
  h+='<p class="tla-tb-empty" hidden>'+esc(t('tbempty'))+'</p>';
  h+='<div class="tla-tb-grid">';
  cards.forEach(function(c){h+=tabItemHTML(c,beta);});
  h+='</div></div></div>';
  return h;
}
/* Filter in place: the cards are already drawn and fitted, so a filter change only shows and
   hides them (no re-render, no re-fit, no lost focus or scroll). */
function tabooApplyFilter(){
  var items=elMain.querySelectorAll('.tla-tb-item'), q=tabFold(tabFilter.q).trim(), shown=0, verTotal=0;
  [].forEach.call(items,function(it){
    var inVer=(it.getAttribute('data-faqv')===tabVersion);   /* the chosen taboo-list version */
    if(inVer)verTotal++;
    var ok=inVer
      &&(!q||it.getAttribute('data-name').indexOf(q)>=0)
      &&(!tabFilter.type||it.getAttribute('data-type')===tabFilter.type)
      &&(!tabFilter.cls||(' '+it.getAttribute('data-factions')+' ').indexOf(' '+tabFilter.cls+' ')>=0)
      &&(!tabFilter.cat||it.getAttribute('data-cat')===tabFilter.cat);
    it.hidden=!ok; if(ok)shown++;
  });
  /* The denominator is this version's card count, not the whole section's. */
  var cnt=elMain.querySelector('[data-tab-count]'); if(cnt)cnt.textContent=shown+' / '+verTotal;
  var empty=elMain.querySelector('.tla-tb-empty'); if(empty)empty.hidden=shown>0;
  /* The clear-filters button and the "download only shows the filtered set" note are relevant
     only while a name/category/type/class filter is narrowing the list (the version picker is not
     one of these). Toggled here so they follow every filter change and the initial state. */
  var hasF=!!(tabFilter.q||tabFilter.type||tabFilter.cls||tabFilter.cat);
  var clr=elMain.querySelector('[data-tabclear]'); if(clr)clr.hidden=!hasF;
  var note=elMain.querySelector('[data-tab-dlnote]'); if(note)note.hidden=!hasF;
}
/* Post-render: fit every card's text to its box (with the real faces), wire the filters and
   apply whatever filter was already set (it persists across a navigate-away-and-back). */
function bindTabooCards(){
  if(!curSec||curSec.kind!=='taboocards'||!window.TabooCard)return;
  TabooCard.fitAll(elMain);
  var q=elMain.querySelector('input[data-tabfilter="q"]');
  if(q)q.addEventListener('input',function(){tabFilter.q=q.value; tabooApplyFilter();});
  [].forEach.call(elMain.querySelectorAll('select[data-tabfilter]'),function(seln){
    seln.addEventListener('change',function(){
      tabFilter[seln.getAttribute('data-tabfilter')]=seln.value; tabooApplyFilter();
    });
  });
  var ver=elMain.querySelector('[data-tabver]');
  if(ver)ver.addEventListener('change',function(){tabVersion=ver.value;
    var sel=TAB_VERSIONS.filter(function(x){return x.id===tabVersion;})[0]; if(sel)ver.title=tabVerLabel(sel);
    tabooApplyFilter();});
  /* Always run once: the version filter hides any card not on the shown list (a no-op today with a
     single version, but correct the moment a second one is added). */
  tabooApplyFilter();
  [].forEach.call(elMain.querySelectorAll('[data-tabdl]'),function(btn){
    btn.addEventListener('click',function(e){ e.stopPropagation();
      var face=btn.closest('.tla-tb-face'); tabooDownload(face&&face.querySelector('.tbc'), btn);
    });
  });
  /* Zoom: the magnifier button, or a click/Enter on the card face itself (but not on its buttons). */
  [].forEach.call(elMain.querySelectorAll('[data-tabzoom]'),function(btn){
    btn.addEventListener('click',function(e){ e.stopPropagation(); tabooZoom(btn.closest('.tla-tb-face')); });
  });
  [].forEach.call(elMain.querySelectorAll('.tla-tb-face'),function(face){
    face.addEventListener('click',function(e){ if(e.target.closest('button')||e.target.closest('a'))return; tabooZoom(face); });
    face.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){e.preventDefault(); tabooZoom(face);} });
  });
  var all=elMain.querySelector('[data-tabdlall]');
  if(all)all.addEventListener('click',function(){
    bleedModal(TABOO_TRIM_MM,tabBleed,function(bleed){tabBleed=bleed; tabooDownloadAll(all);});
  });
  /* Clear filters: reset name/type/class/category (not the version), sync the controls and re-apply. */
  var clr=elMain.querySelector('[data-tabclear]');
  if(clr)clr.addEventListener('click',function(){
    tabFilter.q=''; tabFilter.type=''; tabFilter.cls=''; tabFilter.cat='';
    var qi=elMain.querySelector('input[data-tabfilter="q"]'); if(qi)qi.value='';
    [].forEach.call(elMain.querySelectorAll('select[data-tabfilter]'),function(sn){sn.value='';});
    tabooApplyFilter();
    if(qi)qi.focus();
  });
}
/* Zoom a card face: clone it into a modal, blown up, and re-fit the text to the bigger box. */
/* The label for one face in the zoom carousel — which side/version it is, from its data-face
   (so an investigator's four faces read unambiguously, not two IMPRESA and two TABÚ). */
function tabZoomLabel(f){
  var m={printed:t('tbimpresa'), taboo:t('tbtaboo'),
    'back-printed':t('tbimpresa')+' · '+t('tbback'), 'back-taboo':t('tbtaboo')+' · '+t('tbback'),
    back:t('tbback')};
  return m[f.getAttribute('data-face')]||((f.querySelector('.tla-tb-cap')||{}).textContent||'').trim();
}
/* Zoom a card face into a lightbox that is also a small carousel: left/right arrows (and the arrow
   keys) step through the card's other faces — printed <-> taboo, and an investigator's backs too —
   with a label up top saying which one is shown, so the versions compare side by side without
   leaving the zoom. */
function tabooZoom(startFace){
  if(!startFace)return;
  var item=startFace.closest('.tla-tb-item'); if(!item)return;
  var faces=[].filter.call(item.querySelectorAll('.tla-tb-face'),function(f){return f.querySelector('.tbc');});
  if(!faces.length)return;
  var idx=faces.indexOf(startFace); if(idx<0)idx=0;
  var multi=faces.length>1;
  var prev=document.activeElement;
  var arrow=function(dir,path){return '<button type="button" class="tla-tb-zoomnav tla-tb-zoom'+dir+'" data-zoom'+dir+' aria-label="'+esc(t(dir==='prev'?'tbzoomprev':'tbzoomnext'))+'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'+path+'</svg></button>';};
  var ov=document.createElement('div'); ov.className='tla-tb-zoomov'; ov.setAttribute('role','dialog');
  ov.setAttribute('aria-modal','true'); ov.setAttribute('aria-label',item.getAttribute('data-name')||t('tbtaboo'));
  ov.innerHTML='<div class="tla-tb-zoombox">'
    +'<button type="button" class="tla-tb-zoomclose" aria-label="'+esc(t('close'))+'">&times;</button>'
    +'<div class="tla-tb-zoomhead"><span class="tla-tb-zoomlabel" data-zoomlabel aria-live="polite"></span></div>'
    +'<div class="tla-tb-zoomstage">'
    +(multi?arrow('prev','<path d="M15 18l-6-6 6-6"/>')+arrow('next','<path d="M9 6l6 6-6 6"/>'):'')
    +'<div class="tla-tb-zoomcard" data-zoomcard></div>'
    +'</div></div>';
  (root||document.body).appendChild(ov);
  var host=ov.querySelector('[data-zoomcard]'), labelEl=ov.querySelector('[data-zoomlabel]');
  function show(i){
    idx=((i%faces.length)+faces.length)%faces.length;
    host.innerHTML=faces[idx].querySelector('.tbc').outerHTML;
    labelEl.textContent=tabZoomLabel(faces[idx]);
    if(window.TabooCard)TabooCard.fitAll(host);
  }
  show(idx);
  var close=function(){ try{ov.remove();}catch(e){} document.removeEventListener('keydown',onkey); try{prev&&prev.focus();}catch(e){} };
  var onkey=function(e){
    if(e.key==='Escape'){close(); return;}
    if(multi&&e.key==='ArrowLeft'){e.preventDefault(); show(idx-1); return;}
    if(multi&&e.key==='ArrowRight'){e.preventDefault(); show(idx+1); return;}
    if(e.key==='Tab'){var f=[].slice.call(ov.querySelectorAll('button')); if(!f.length)return;
      e.preventDefault(); var j=f.indexOf(document.activeElement);
      (e.shiftKey?f[(j<=0?f.length-1:j-1)]:f[(j+1)%f.length]).focus();}
  };
  ov.addEventListener('click',function(e){
    if(e.target===ov||e.target.closest('.tla-tb-zoomclose')){close(); return;}
    if(e.target.closest('[data-zoomprev]')){show(idx-1); return;}
    if(e.target.closest('[data-zoomnext]')){show(idx+1); return;}
  });
  document.addEventListener('keydown',onkey);
  var cb=ov.querySelector('.tla-tb-zoomclose'); if(cb)cb.focus();
}
/* ---- downloading a taboo card ----
   The card is a plate with DOM text over it (js/taboo.js). To save it we redraw it onto a canvas
   at the plate's own resolution: the plate first, then every text fragment and symbol exactly where
   the browser laid it out — read off the DOM through Range rectangles — so the file matches the
   screen, wrapping, fonts and icons included. Same untainted, dependency-free approach as the UB
   viewer, extended for the taboo card's richer body. */
var TAB_FONT_SPECS=['40px ubtitle','40px ubbody','700 40px ubbody','italic 40px ubbody','italic 700 40px ubbody','40px bolton'];
function tabooFontsReady(){
  var d=window.document&&document.fonts;
  if(!d||!d.load)return Promise.resolve();
  return Promise.all(TAB_FONT_SPECS.map(function(f){return d.load(f).catch(function(){});}))
    .then(function(){return d.ready;})
    .then(function(){try{var c=document.createElement('canvas').getContext('2d');
      TAB_FONT_SPECS.forEach(function(f){c.font=f;c.fillText(' ',-20,-20);});}catch(e){}}).catch(function(){});
}
function tabooCardToBlob(card,mime,quality){
  return new Promise(function(resolve){
    if(!card){resolve(null);return;}
    var dimg=card.querySelector('.tbc-pic');
    if(!dimg||!dimg.naturalWidth){resolve(null);return;}
    var code=card.getAttribute('data-code'), isBack=card.classList.contains('tbc-back');
    var type=card.getAttribute('data-type')||'';
    /* Investigators are landscape; turn the finished download upright (front +90, back +270). */
    var rot=type==='investigator'?90:type==='investigator-back'?270:0;
    var suffix=isBack?'-back':'';
    /* Draw the download from the PRINT-res trim plate (1476px, ~590dpi), falling back to the display
       plate if the hi-res file is missing. When bleed is asked for, use the FULL-bleed plate
       (1644x2244 / 2244x1644) whose 72px margin is REAL card art — not an edge stretch. */
    tabooFontsReady().then(function(){ loadImg('assets/taboo/plates-hi/'+code+suffix+'.webp').then(function(hi){
      var red=(hi&&hi.naturalWidth)?hi:dimg;
      (tabBleed?loadImg('assets/taboo/plates-bleed/'+code+suffix+'.webp'):Promise.resolve(null)).then(function(full){
      var CW=red.naturalWidth, CH=red.naturalHeight;   // the reduced/trim size = the on-screen card box
      var cr=card.getBoundingClientRect(), sc=CW/cr.width;
      var useBleed=!!(tabBleed&&full&&full.naturalWidth);
      var cv=document.createElement('canvas'), ctx, X, Y;
      if(useBleed){
        /* Scale the full plate so its trim (72px bleed on a 1500x2100 / 2100x1500 trim) lands
           exactly on the reduced box: every %-calibrated glyph then falls in the trim, and the
           margin around it is the plate's own bleed art. */
        var portrait=CH>=CW, trimW=portrait?1500:2100, trimH=portrait?2100:1500;
        var mx=Math.round(72*CW/trimW), my=Math.round(72*CH/trimH);
        cv.width=CW+2*mx; cv.height=CH+2*my; ctx=cv.getContext('2d');
        ctx.drawImage(full,0,0,cv.width,cv.height);
        X=function(px){return mx+(px-cr.left)*sc;}; Y=function(py){return my+(py-cr.top)*sc;};
      }else{
        cv.width=CW; cv.height=CH; ctx=cv.getContext('2d');
        ctx.drawImage(red,0,0,CW,CH);
        X=function(px){return (px-cr.left)*sc;}; Y=function(py){return (py-cr.top)*sc;};
      }
      var iconJobs=[];
      /* One inline symbol: its own SVG mask, tinted with the element's colour, at its box. */
      function drawIcon(el){
        var cs=getComputedStyle(el), m=cs.maskImage||cs.webkitMaskImage||'';
        var url=(m.match(/url\(["']?([^"')]+)/)||[])[1]; if(!url)return;
        var r=el.getBoundingClientRect(), w=Math.max(1,r.width*sc), h=Math.max(1,r.height*sc);
        var tint=cs.backgroundColor||'#231f20';
        iconJobs.push(new Promise(function(res){
          var im=new Image(); im.crossOrigin='anonymous';
          im.onload=function(){
            var tc=document.createElement('canvas'); tc.width=w; tc.height=h;
            var tx=tc.getContext('2d'); tx.drawImage(im,0,0,w,h);
            tx.globalCompositeOperation='source-in'; tx.fillStyle=tint; tx.fillRect(0,0,w,h);
            ctx.drawImage(tc,X(r.left),Y(r.top)); res();
          };
          im.onerror=function(){res();}; im.src=url;
        }));
      }
      /* The Spanish traits separator: a small rotated square in the text colour. */
      function drawDiamond(el){
        var r=el.getBoundingClientRect(), cs=getComputedStyle(el);
        var cx=X((r.left+r.right)/2), cy=Y((r.top+r.bottom)/2), rad=r.width*sc/2;
        ctx.save(); ctx.translate(cx,cy); ctx.rotate(Math.PI/4);
        ctx.fillStyle=cs.backgroundColor||'#231f20'; ctx.fillRect(-rad,-rad,rad*2,rad*2); ctx.restore();
      }
      /* A run of text: drawn word by word at each word's own on-screen box, so the browser's
         wrapping is reproduced without re-wrapping. Bold/italic/colour/stroke come off the DOM. */
      function drawText(node){
        var parent=node.parentElement; if(!parent)return;
        var cs=getComputedStyle(parent);
        ctx.font=cs.fontStyle+' '+cs.fontWeight+' '+(parseFloat(cs.fontSize)*sc)+'px '+cs.fontFamily;
        ctx.fillStyle=cs.color; ctx.textBaseline='middle'; ctx.textAlign='left';
        var strokeW=parseFloat(cs.getPropertyValue('-webkit-text-stroke-width'))*sc||0;
        var strokeC=cs.getPropertyValue('-webkit-text-stroke-color')||'#000';
        var order=(cs.paintOrder||'').indexOf('stroke')===0;
        var text=node.nodeValue, re=/\S+/g, m;
        while((m=re.exec(text))){
          var range=document.createRange();
          range.setStart(node,m.index); range.setEnd(node,m.index+m[0].length);
          var rects=range.getClientRects(); if(!rects.length)continue;
          var r=rects[0], x=X(r.left), y=Y((r.top+r.bottom)/2), w=m[0];
          if(strokeW>0&&order){ctx.lineJoin='round'; ctx.lineWidth=strokeW; ctx.strokeStyle=strokeC; ctx.strokeText(w,x,y);}
          ctx.fillText(w,x,y);
          if(strokeW>0&&!order){ctx.lineJoin='round'; ctx.lineWidth=strokeW; ctx.strokeStyle=strokeC; ctx.strokeText(w,x,y);}
        }
      }
      var walker=document.createTreeWalker(card,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT,{acceptNode:function(n){
        if(n.nodeType===3)return n.nodeValue&&n.nodeValue.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;
        var cl=n.classList||{contains:function(){return false;}};
        if(cl.contains('tbc-pic'))return NodeFilter.FILTER_REJECT;
        if(cl.contains('ico')||cl.contains('tbc-set')||cl.contains('tbc-tsep'))return NodeFilter.FILTER_ACCEPT;
        return NodeFilter.FILTER_SKIP;
      }});
      var n;
      while((n=walker.nextNode())){
        if(n.nodeType===1){
          if(n.classList.contains('tbc-tsep'))drawDiamond(n);
          else drawIcon(n);
        } else drawText(n);
      }
      Promise.all(iconJobs).then(function(){
        /* Bleed asked for but no full-bleed plate (e.g. an investigator back not yet generated):
           keep the old edge-clamp so the size still matches. Otherwise the plate already carries
           real bleed art. Finally, turn a landscape investigator upright. */
        var out=(tabBleed&&!useBleed)?addBleed(cv):cv;
        out=rotateCanvas(out,rot);
        out.toBlob(function(b){resolve(b);},mime||'image/png',quality);
      });
      }); }); });
  });
}
function tabooSanitize(n){return String(n||'card').replace(/[\/\\:*?"<>|]+/g,'').replace(/\s+/g,' ').trim();}
var TABOO_BACK_URL='assets/taboo/back.webp';   // the standard player-card back, trimmed (no bleed)
/* What a single item actually contributes to a download, in order. The PRINTED face is never
   exported (it is only shown for comparison). A normal card gives its TABOO face followed by the
   shared player back. An investigator is landscape and deck-building on the back: the two whose
   BACK is also tabooed (Lola, Mandy) export front + reconstructed back; the others export only the
   front. Mandy's front is unchanged, so her pair takes the printed front with the tabooed back. */
function tabooItemExports(item){
  var type=item.getAttribute('data-type');
  var printed=item.querySelector('.tla-tb-face[data-face="printed"] .tbc');
  var taboo=item.querySelector('.tla-tb-face[data-face="taboo"] .tbc');
  /* The printable back is the tabooed one where it exists (Lola, Mandy), else the plain back. The
     original back (back-printed) is shown for comparison only, never exported. */
  var backEl=item.querySelector('.tla-tb-face[data-face="back-taboo"] .tbc')
           ||item.querySelector('.tla-tb-face[data-face="back"] .tbc');
  var out=[];
  if(type==='investigator'){
    var front=item.hasAttribute('data-frontsame')?printed:(taboo||printed);
    if(front)out.push({card:front, side:'front'});
    /* Every investigator prints double-sided, so the back always ships — the reconstructed taboo
       back for Lola/Mandy, the unchanged printed back for Rex/Trish. */
    if(backEl)out.push({card:backEl, side:'back'});
  }else{
    var face=taboo||printed;
    if(face)out.push({card:face, side:'card'});
    out.push({shared:true, side:'back'});
  }
  return out;
}
/* The file name for one export entry: "<name> <code> - Tabú_01 - Sin sangrado" for the card,
   "…Tabú_02 - Con sangrado" for its back, and the investigator sides spelled out. The bleed choice
   (i18n) goes in the name so a reader can tell the with/without copies apart. */
function tabooExportName(item, entry){
  var code=item.getAttribute('data-code')||'', name=item.getAttribute('data-name')||code;
  var base=t('tbtaboo');
  if(item.getAttribute('data-type')==='investigator') base+=' '+t(entry.side==='back'?'tbback':'tbfront');
  var bleed=' - '+(tabBleed?t('tbwithbleed'):t('tbnobleed'));
  return tabooSanitize(name+' '+code+' - '+base+(entry.side==='back'?'_02':'_01')+bleed);
}
/* The shared player-card back as a blob. Without bleed, the trimmed back 1:1. WITH bleed, the
   FULL-bleed back scaled so its trim lands exactly where the front's does (front bleed output is the
   1476x2096 trim + a 71/72 px margin), so a front and this back print the SAME size for duplex — the
   margin is the back's own art, never an edge stretch. */
function tabooBackBlob(mime, quality){
  var url=tabBleed?'assets/taboo/back-bleed.webp':TABOO_BACK_URL;
  return loadImg(url).then(function(im){
    if(!im||!im.naturalWidth){
      if(tabBleed)return imageToPngBlob(TABOO_BACK_URL, true);   // last-resort: stretch the trimmed back
      return null;
    }
    var cv=document.createElement('canvas'), ctx;
    if(tabBleed){
      var CW=1476, CH=2096, mx=Math.round(72*CW/1500), my=Math.round(72*CH/2100);
      cv.width=CW+2*mx; cv.height=CH+2*my; ctx=cv.getContext('2d');
      ctx.drawImage(im,0,0,cv.width,cv.height);
    }else{
      cv.width=im.naturalWidth; cv.height=im.naturalHeight; ctx=cv.getContext('2d');
      ctx.drawImage(im,0,0);
    }
    return new Promise(function(res){ cv.toBlob(function(b){res(b);}, mime||'image/png', quality); });
  });
}
/* Download one item: its taboo card (and, where it has one, its back). A single download saves that
   card and its back only, as PNG. */
function tabooDownload(cardEl,btn){
  var item=cardEl&&cardEl.closest('.tla-tb-item'); if(!item)return;
  if(btn)btn.setAttribute('aria-busy','true');
  var entries=tabooItemExports(item), seq=tabooFontsReady();
  entries.forEach(function(e){
    seq=seq.then(function(){
      return (e.shared?tabooBackBlob('image/png'):tabooCardToBlob(e.card,'image/png'))
        .then(function(b){ if(b)ubSaveBlob(b, tabooExportName(item,e)+'.png'); });
    });
  });
  seq.then(function(){ if(btn)btn.removeAttribute('aria-busy'); },function(){ if(btn)btn.removeAttribute('aria-busy'); });
}
/* Every visible item as one .zip, each card immediately followed by its back (many copies of the
   shared back, as the reader asked). Rendered off the on-screen cards, several at a time. JPEG q.95
   keeps the whole-set archive a fifth of a lossless PNG's size while staying print-clean. */
function tabooDownloadAll(btn){
  var items=[].slice.call(elMain.querySelectorAll('.tla-tb-item')).filter(function(it){return !it.hidden;});
  var entries=[]; items.forEach(function(it){ tabooItemExports(it).forEach(function(e){ entries.push({item:it, e:e}); }); });
  if(!entries.length)return;
  var label=btn&&btn.querySelector('.tla-tb-dlall-label'), orig=label?label.textContent:'';
  if(btn){btn.disabled=true; btn.setAttribute('aria-busy','true'); if(label)label.textContent=t('ubdownallwait');}
  var slots=new Array(entries.length), total=entries.length, done=0;
  var tick=function(){ done++; if(label)label.textContent=done+' / '+total; };
  var finish=function(){ if(btn){btn.disabled=false; btn.removeAttribute('aria-busy'); if(label)label.textContent=orig;} };
  /* The shared player back is identical for every normal card, so render it once and reuse the bytes
     under each card's own back-name instead of re-encoding it 90 times. */
  var backBytesP=null;
  var backBytes=function(){ if(!backBytesP)backBytesP=tabooBackBlob('image/jpeg',0.95).then(function(b){return b?b.arrayBuffer().then(function(ab){return new Uint8Array(ab);}):null;}); return backBytesP; };
  tabooFontsReady().then(function(){
    return renderPool(entries, function(ent,idx){
      var e=ent.e, nm=tabooExportName(ent.item,e)+'.jpg';
      if(e.shared) return backBytes().then(function(u8){ if(u8)slots[idx]={name:nm, data:u8}; });
      return tabooCardToBlob(e.card,'image/jpeg',0.95).then(function(b){
        if(b)return b.arrayBuffer().then(function(ab){ slots[idx]={name:nm, data:new Uint8Array(ab)}; });
      });
    }, 6, tick);
  }).then(function(){
    finish(); var files=slots.filter(Boolean);
    if(files.length)ubSaveBlob(ubZip(files),tabooSanitize('the-living-arkham-taboo-'+lang)+(tabBleed?'-bleed':'-nobleed')+'.zip');
  }).catch(function(){ finish(); });
}
/* A blocking loader for the one slow render, the taboo gallery. Its spinner is a CSS transform
   animation, so it keeps turning on the compositor even while the main thread is frozen fitting
   ~190 card faces; the full-screen overlay stops the reader tapping other things meanwhile. */
function showLoading(){ var el=document.getElementById('tla-loading'); if(el)el.hidden=false; }
function hideLoading(){ var el=document.getElementById('tla-loading'); if(el)el.hidden=true; }
/* A pointer from a rules-text chapter to its live interactive VIEWER in Resources, where the same
   cards can be browsed and downloaded. `key` is the target viewer's section key: 'ultimatums' (the
   Ultimatums/Boons/Refractions gallery) or 'taboos' (the taboo-list card viewer). Shown only where
   that viewer is actually live in this language — a book-less language has neither the rule text
   nor the viewer content, and the taboo viewer stays a "coming soon" placeholder until its cards
   load (attachTabooCards flips its kind to 'taboocards'), so there is nothing to point at. The link
   is a normal xref, so from the FAQ it goes through the usual cross-corpus confirm (faq1 -> grimoire). */
function xrefBannerHTML(key){
  var v=null,i; for(i=0;i<data.sections.length;i++){ if(data.sections[i].key===key){v=data.sections[i];break;} }
  if(!v)return '';
  var u=v.ub, live = key==='ultimatums'
    ? !!(u&&((u.ultimatums||[]).length||(u.boons||[]).length||(u.refractions||[]).length))
    : v.kind!=='placeholder';
  if(!live)return '';
  var link='<a class="xref" href="#'+esc(lang)+'/'+esc(v.id)+'" data-t="'+esc(v.id)+'">'+esc(v.title)+'</a>';
  var p=String(t('ubxref')||'').split('{link}');
  var txt=p.length<2?esc(p[0]||''):esc(p[0])+link+esc(p[1]||'');
  return '<aside class="tla-xrefbanner">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="8" width="9" height="12" rx="1.5" transform="rotate(-15 12 20)"/><rect x="11" y="8" width="9" height="12" rx="1.5" transform="rotate(15 12 20)"/></svg>'
    +'<p class="tla-xrefbanner-t">'+txt+'</p></aside>';
}
function render(sid,eid,flash){
  var s=data.sections.filter(function(x){return x.id===sid;})[0]; if(!s)s=data.sections[0];
  curSec=s;
  /* The taboo card gallery wants the horizontal room a prose column does not: it collapses the
     right-hand "on this page" rail (empty here anyway) so two large cards sit side by side. Set
     on every path, so navigating away restores the rail. */
  var shell=document.querySelector('.tla-body'); if(shell)shell.classList.toggle('is-wide', s.kind==='taboocards');
  if(s.kind==='whatsnew'){renderWhatsNew(); markNav(sid); return;}
  if(s.kind==='intro'){renderLanding(s); markNav(sid); return;}
  var ents=visibleEntries(s);
  var h='<div class="tla-doc'+(s.kind==='taboocards'?' tla-doc--wide':'')+'">';
  h+='<div class="tla-crumb">'+(s.num?('· '+s.num+' ·'):'')+' The Living Arkham</div>';
  h+='<h1 class="tla-h1">'+(s.num?'<span class="tla-rn">'+s.num+'.</span>':'')+esc(s.title)+'</h1>';
  h+='<div class="tla-rule"></div>';
  /* Below a FAQ chapter's title (the whole chapter IS the topic): a pointer to its live viewer in
     Resources. The grimoire's optional-rules chapter mixes topics, so ITS ultimatums banner is
     placed under the "Ultimatums and Boons" heading instead (in the entries loop below). */
  if(s.key==='faq-optional')h+=xrefBannerHTML('ultimatums');
  else if(s.key==='faq-taboos')h+=xrefBannerHTML('taboos');
  /* This language has the interface but not the books. Say so here, on the chapter the reader
     actually opened, and hand them the same chapter in a language that has it — the ids are
     shared with that language precisely so this link can exist (see bookShell). */
  if(s.nobook)h+=nobookHTML(s);
  /* The retired FAQ's Beta environments are superseded by the Grimoire's optional-rules
     environments. Flag it loudly, like the book's own STOP! callout, and point at the living
     definition — so no one reads this obsolete text as current. */
  if(s.key==='faq-environments'){
    var envt=grimoireEnvTarget();
    h+='<aside class="tla-obsolete" role="note">'
      +'<div class="tla-obsolete-tag">'+esc(t('obsoleteword'))+'</div>'
      +'<div class="tla-obsolete-body"><p class="tla-obsolete-lead">'+esc(t('envobsolete'))+'</p>'
      +(envt?'<a class="tla-obsolete-go" href="#'+lang+'/'+esc(envt)+'">'+esc(t('envobsoletego'))+' <span aria-hidden="true">→</span></a>':'')
      +'</div></aside>';
  }
  /* The FAQ opens by saying what it covers — and the one thing a reader most needs to know
     before reading a word of it is that it is NOT the current ruleset. Same loud callout as
     the obsolete environments, on the chapter that introduces the whole shelf. */
  if(s.key==='faq-intro'){
    h+='<aside class="tla-obsolete" role="note">'
      +'<div class="tla-obsolete-tag">'+esc(t('noticeword'))+'</div>'
      +'<div class="tla-obsolete-body"><p class="tla-obsolete-lead">'+esc(t('c1scope'))+'</p>'
      +'<p class="tla-obsolete-p">'+esc(t('c1scopebody'))+'</p>'
      +'</div></aside>';
  }
  /* First thing under the title: the diagrams ARE the summary, so the offer to read
     only them belongs where it is seen before the reading starts. */
  if(hasDiagrams(s)||s.fanmade)h+=diagSwitch(s);
  h+=verSwitch(s);
  /* The lead is prose too, so diagrams-only hides it. That is the whole feature in a
     chapter the book writes as one procedure with a single diagram at the end. */
  if(s.intro&&s.intro.length&&!fmOnly()&&!(diagOnly()&&hasDiagrams(s))){h+='<div class="tla-lead">'+blocksHTML(s.intro,false,s.kind==='icons'&&!!s.qr)+'</div>';}
  if(s.kind==='anatomy'){h+=anatomyHTML(s);}
  if(s.kind==='icons'){h+=iconsHTML(s);}
  if(s.kind==='ultimatums'){h+=ubHTML(s);}
  if(s.kind==='taboocards'){h+=tabooCardsHTML(s);}
  if(s.taboos){h+=taboosHTML(s);}
  if(s.reprints){h+=reprintsHTML(s);}
  /* quickref renders its text sub-sections through the normal entries loop below (so
     their terms autolink to the glossary and they land in the table of contents), then
     the colour symbol key and the downloadable image after them — the sheet read top to
     bottom: the phases and terms first, the icon legend next, the printable sheet last.
     A banner up top points to that download, the way the book flags its own callouts. */
  if(s.kind==='quickref'&&s.figures&&s.figures.length){
    h+='<aside class="tla-qrbanner">'
      +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
      +'<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>'
      +'<p class="tla-qrbanner-t">'+esc(t('qrbanner'))+'</p>'
      +'<button type="button" class="tla-qrbanner-go">'+esc(t('qrbannergo'))+'</button></aside>';
  }
  /* Announced, not written. The book does the same with its own empty icon groups, and
     the reason is the same: saying a thing is coming tells the reader the site knows
     about it, where an absence tells them nothing at all. */
  if(s.kind==='placeholder'){
    h+='<div class="tla-soon"><p class="tla-soon-h">'+esc(t('soon'))+'</p>'
      +'<p class="tla-soon-d">'+esc(t('soondesc'))+'</p></div>';
  }
  if(s.figures&&s.figures.length&&s.kind!=='quickref'){
    h+='<div class="tla-figs">';
    s.figures.forEach(function(f){
      h+='<figure class="tla-fig"><img loading="lazy" src="assets/img/'+esc(f.file)+'" alt=""><figcaption>'+t('fig')+' '+f.page+'</figcaption></figure>';
    });
    h+='</div>';
  }
  /* …but only when there is something to filter. A language with no rulebook of its own has
     the glossary's shelf and none of its entries, and a "filter by letter" control over an
     empty list is a button that does nothing — worse than absent, because a keyboard reaches
     it and a screen reader announces it. */
  if(s.kind==='glossary'&&glossBase(s).length){h+=azFilterBar(s);}
  /* A glossary filter can narrow to nothing — a letter with no entries under the active
     version. Say so, rather than leave a blank void that reads as "this section is
     empty". Only the glossary needs it; every other kind always has content. */
  if(s.kind==='glossary' && !ents.length){h+='<p class="tla-glossnone">'+esc(t('glossnone'))+'</p>';}
  var lv=latestV();
  /* The grimoire's optional-rules chapter mixes topics, so the ultimatums-viewer banner goes under
     the "Ultimatums and Boons" heading rather than at the chapter top. That heading is the entry
     right before the "Ultimatums" card list, whose title is t('ubultimatums') in every language. */
  var ubHeadId=null;
  if(s.key==='optional-rules'){
    for(var uhi=0;uhi<ents.length;uhi++){ if(ents[uhi].title===t('ubultimatums')){ if(uhi>0)ubHeadId=ents[uhi-1].id; break; } }
  }
  ents.forEach(function(e){
    /* An entry that is wholly new needs no per-word diff marks — the badge
       already says so. One that was rewritten does: the marks are the point. */
    var brandNew=lv&&isNewIn(e,lv);
    /* role comes from how the book prints the heading: a STOP! callout, the
       opening of a subsection, or nothing special. */
    var role=e.role?(' is-'+e.role):'';
    /* h2: an entry sits directly under the chapter's h1. Jumping straight to h3
       would leave a hole in the outline a screen reader navigates by. */
    /* data-kind, so a chapter can style its own entries without the CSS having to
       know a section id or a title. The FAQ uses it to set the answer in from the
       question — the book runs both flush left, so the indent is ours, and it is what
       makes a page of alternating questions and answers scannable. */
    h+='<article class="tla-entry'+role+(brandNew?' is-new':'')+(lv&&isChangedIn(e,lv)?' is-upd':'')
      +'" data-kind="'+esc(s.kind)+'" id="e-'+esc(e.id)+'">';
    h+='<h2>'+titleHTML(e)+diagBadge(e)+verBadge(e)+'<a class="anchor" href="#'+lang+'/'+esc(e.id)+'" title="'+esc(t('jump'))+'" aria-label="'+esc(t('jump'))+'">§</a></h2>';
    if(ubHeadId&&e.id===ubHeadId)h+=xrefBannerHTML('ultimatums');
    h+=e.table?substHTML(e):(e.flow?flowHTML(e):blocksHTML(e.blocks,brandNew));
    h+=qrLinkHTML(e);
    h+=extrasHTML(e);
    h+=verProvenance(e);
    h+=figuresHTML(e,esc(e.id));
    h+='</article>';
  });
  /* After the text: the colour symbol key, then the whole sheet as a download. */
  if(s.kind==='quickref'){
    h+=quickrefHTML(s);
    (s.figures||[]).forEach(function(f){
      /* The image is a KEEPSAKE — the whole sheet in one file to print or save — so it
         names itself a download and carries a real download link, an addition to the
         interactive version above rather than the only version. */
      h+='<figure class="tla-fig is-download" id="qr-download"><img loading="lazy" src="assets/img/'+esc(f.file)+'" alt="'+esc(t('qrimgalt'))+'">'
        +'<figcaption><a class="tla-dl" href="assets/img/'+esc(f.file)+'" download>'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
        +'<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>'
        +esc(t('qrdownload'))+'</a></figcaption></figure>';
    });
  }
  /* The community's diagram sits after the book's own text and diagram — an appendix, never a
     substitute — unless the reader asked for it alone. */
  if(s.fanmade&&!diagOnly())h+=fanmadeHTML(s);
  h+='</div>';
  markNav(sid);                // highlight the nav now, not after a 10-15 s taboo render
  var commit=function(){
    elMain.innerHTML=h;
    syncStickyHeight();        // before any scroll-to, so the target clears the toolbar
    layoutFlowLoops();
    bindAnatomy();
    bindUB();
    bindTabooCards();
    [].forEach.call(elMain.querySelectorAll('.tla-subst'),substFilter);
    buildToc(s,ents);
    if(eid){var el=document.getElementById('e-'+eid); if(el){el.scrollIntoView({block:'start'}); if(flash){el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}}}
    else{elMain.scrollTop=0;}
    hideLoading();
  };
  /* The taboo gallery parses ~190 card faces and fits each to its box — 10-15 s of synchronous work
     on a phone, with nothing on screen. Put a blocking loader up first and yield TWICE so the browser
     paints it before the freeze; every other section is fast enough to commit straight away. */
  if(s.kind==='taboocards' && window.requestAnimationFrame){
    elMain.innerHTML=''; elMain.scrollTop=0;   // clear the previous section so the loader sits on a clean dark ground, not the page you came from
    showLoading();
    requestAnimationFrame(function(){ requestAnimationFrame(commit); });
  } else {
    commit();
  }
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
/* The active What's New page belongs to a corpus: the grimoire's reads data.versions/
   data.whatsnew, the FAQ chapter 1's reads its own history, carried on its section. */
function wnData(){
  var s=curSec;
  if(s&&s.corpusWhatsnew)return {versions:s.corpusVersions||[],whatsnew:s.corpusWhatsnew||{},corpus:s.corpus||'grimoire'};
  return {versions:data.versions||[],whatsnew:data.whatsnew||{},corpus:'grimoire'};
}
function wnVersions(){
  /* newest first: history reads backwards */
  var wd=wnData();
  return (wd.versions||[]).filter(function(v){return wd.whatsnew&&wd.whatsnew[v.v];}).reverse();
}
/* "There is a newer edition, but not in your language yet." Named languages, a
   real date, and a way straight into the edition that does exist — a notice the
   reader can act on rather than just be told. */
function pendingHTML(corpus){
  var ahead=langsAhead(lang,corpus); if(!ahead.length)return '';
  var top=ahead[0];
  var names=ahead.map(function(L){return langName(L.code);}).join(', ');
  var h='<section class="tla-pending">';
  h+='<i class="tla-eldersign tla-pending-star" aria-hidden="true"></i>';
  h+='<div class="tla-pending-body">';
  h+='<h2 class="tla-pending-t">'+esc(t('pendingt').replace('{v}',top.v).replace('{l}',names))+'</h2>';
  h+='<p class="tla-pending-d">'+esc(t('pendingd').replace('{v}',top.v)
      .replace('{d}',fmtDate(top.date)).replace('{l}',names))+'</p>';
  /* Switching language is what this button does, so it says so: the reader is
     about to leave their own language, and that should not be a surprise.
     No lang="" on it: the label is written in the READER's language ("Ver las
     novedades en inglés"), so tagging it as English would have a screen reader
     read Spanish aloud with an English voice. */
  h+='<button class="tla-pending-cta" type="button" data-golang="'+esc(top.code)+'">'
    +esc(t('pendingcta').replace('{l}',langName(top.code)))+' →</button>';
  h+='</div></section>';
  return h;
}
function renderWhatsNew(){
  var wd=wnData();
  var vs=wnVersions();
  var pending=pendingHTML(wd.corpus);
  if(!vs.length && !pending){elMain.innerHTML=''; elToc.innerHTML=''; return;}
  var cur=null;
  for(var i=0;i<vs.length;i++){if(vs[i].v===wnPick)cur=vs[i];}
  if(!cur)cur=vs[0];
  var wn=cur?wd.whatsnew[cur.v]:null;

  var h='<div class="tla-doc">';
  h+='<div class="tla-crumb">The Living Arkham</div>';
  h+='<h1 class="tla-h1">'+esc(t('news'))+'</h1><div class="tla-rule"></div>';
  h+=pending;

  // the whole history, always — one chip per edition, newest first. It still
  // matters when there is no news: it says which edition you are actually on.
  h+='<div class="tla-vertabs" role="group" aria-label="'+esc(t('history'))+'">';
  vs.forEach(function(v){
    var n=wd.whatsnew[v.v], count=n['new'].length+n.updated.length;
    h+='<button class="tla-vertab'+(cur&&v.v===cur.v?' active':'')+'" type="button" data-wnv="'+esc(v.v)+'"'
      +' aria-pressed="'+(!!cur&&v.v===cur.v)+'">'
      +'<span class="tla-vertab-v">v'+esc(v.v)+'</span>'
      +'<span class="tla-vertab-d">'+esc(fmtDate(v.date))+'</span>'
      +'<span class="tla-vertab-n">'+count+'</span></button>';
  });
  var first=(wd.versions||[])[0];
  if(first && !wd.whatsnew[first.v]){
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
/* One row per chapter, not one per entry.

   The FAQ is the reason. An edition that answers eighty questions would arrive as eighty
   cards, and the three rules changes worth knowing about would be buried among them —
   which is exactly backwards, since a chapter is the unit a reader scans by and an entry
   is what they open once they know where to look. So the chapter is the row and its
   entries live inside it. This is not a FAQ special case: the glossary will get there.

   Native <details>: keyboard-operable, announced as expandable, and remembers nothing —
   none of which is ours to get right. All start collapsed: a mix of open and shut rows
   read as noise (some chapters "done", others not), so every chapter is a shut row the
   reader opens on purpose. */
function wnList(items,cls){
  var by={}, order=[];
  items.forEach(function(it){
    var k=it.sid||it.sec||'?';
    if(!by[k]){by[k]={items:[], sec:it.sec, num:it.num}; order.push(k);}
    by[k].items.push(it);
  });
  var h='';
  order.forEach(function(k){
    var g=by[k], n=g.items.length;
    h+='<details class="tla-wngrp">';
    h+='<summary class="tla-wngrp-s">'
      +(g.num?('<span class="tla-wngrp-n">'+esc(g.num)+'</span>'):'<span class="tla-wngrp-n">•</span>')
      +'<span class="tla-wngrp-t">'+esc(g.sec)+'</span>'
      +'<span class="tla-wngrp-c '+cls+'">'+n+' '+esc(plural('entries',n))+'</span></summary>';
    h+='<div class="tla-wngrid">';
    g.items.forEach(function(it){
      /* The card already says "rewritten", so the title's own diff marks would only
         repeat it — same reason titleHTML suppresses them. */
      h+='<button class="tla-wncard '+cls+(it.chapter?' is-chapter':'')+'" type="button" data-eid="'+esc(it.id)+'">'
        +'<span class="tla-wntitle">'+(it.titleRuns?runsHTML(it.titleRuns,true):esc(it.title))+'</span>'
        // a whole chapter can change too — the FAQ gains answers in its own lead text
        +(it.chapter?('<span class="tla-wnsec">'+esc(t('chapter'))+'</span>'):'')+'</button>';
    });
    h+='</div></details>';
  });
  return h;
}
/* "Rincón Miskatonic" is the project's proper name (a Spanish-language site), so it is set in
   italics wherever it is named — the same way a publication title is. The label is translated as
   usual; only the name inside it is emphasised. Escaped first, then the (accented, HTML-safe) name
   is wrapped, so this stays injection-safe. */
function rmName(s){
  return esc(s).replace(/Rincón Miskatonic/g,'<em class="tla-rm-name">Rincón Miskatonic</em>');
}
function rmPanel(){
  return '<section class="tla-rm">'
    +'<div class="tla-rm-body">'
      +'<h2 class="tla-rm-title">'+rmName(t('rmtitle'))+'</h2>'
      +'<p>'+t('rmbody')+'</p>'
      +'<a class="tla-rm-cta" href="'+BLOG+'" target="_blank" rel="noopener">'+rmName(t('rmcta'))+' <span aria-hidden="true">↗</span></a>'
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
  {id:'relevant',    keys:['whatsnew','glossary','errata-viewer','faq-errata']},
  {id:'recommended', keys:['timing','skill-tests','errata','faq','faq-questions']},
  {id:'extra',       keys:['ultimatums','taboos']}
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

/* What a chapter card says it holds.
   "0 entradas" was on eight of the sixteen cards, and it read as "this chapter is
   empty" — while Preparación shows 3.337 characters of rules. The count was not
   unhelpful, it was measuring the wrong axis: entries are the NAMED SUBSECTIONS you
   can jump to, and the book writes several chapters as one continuous procedure with
   no subsections at all. So the count is only used where entries are what the chapter
   is built from, and every other shape says what it actually is.
   One entry is not a structure either — Pruebas de habilidad has a single entry (the
   diagram) and 27 blocks of lead, so "1 entrada" would describe the chapter by its one
   heading and repeat the same mistake in the other direction. */
function prodIconCount(s2){
  var n=0; (s2.groups||[]).forEach(function(g){n+=(g.items||[]).length;}); return n;
}
function cardMeta(s2){
  var bits=[];
  /* What the section IS, not how big it is — a reader browsing the shelf wants "terms
     and keywords, A to Z", not "163 entries". The blurb is the pack's, keyed by the
     language-neutral section key. Novedades keeps its version line (handled by its
     caller); a section with no blurb falls back to a count so nothing renders blank. */
  var blurb=pick(lang,'blurbs',s2.key);
  if(blurb)                          bits.push(blurb);
  else{
    var n=sectionEntries(s2).length;
    var figs=(s2.figures||[]).length, keys=(s2.keys||[]).length, lead=(s2.intro||[]).length;
    if(s2.kind==='figures'&&figs)      bits.push(figs+' '+plural('plates',figs));
    else if(s2.kind==='anatomy'&&keys) bits.push(keys+' '+plural('cardkeys',keys));
    else if(s2.kind==='icons')         bits.push(prodIconCount(s2)+' '+t('iconscard'));
    else if(s2.kind==='quickref')      bits.push(qrefSymbolCount()+' '+t('qrsymbols'));
    else if(n>1)                       bits.push(n+' '+plural('entries',n));
    else if(lead)                      bits.push(t('prosechapter'));
    else if(n)                         bits.push(n+' '+plural('entries',n));
  }
  /* Flowed as text, not an icon with an aria-label: the card's accessible name is
     built from its contents, so this lands in it for free and a screen reader gets
     the same sentence the sighted reader does. It is not a second pennant — the two
     chapters that draw diagrams are already the two flying "Sección recomendada", so
     a ribbon could not single them out from anything, and the card only has one
     ribbon slot anyway. */
  if(hasDiagrams(s2))                bits.push(t('carddiagrams'));
  return bits.join(' · ');
}

function renderLanding(s){
  var li=latestInfo(data);
  var h='<div class="tla-doc tla-landing">';
  h+='<div class="tla-hero"><div class="tla-hero-inner">';
  h+='<h1 class="tla-hero-title">The Living Arkham</h1>';
  h+='<p class="tla-hero-sub">'+esc(t('sub'))+'</p>';
  h+='</div>';
  /* The banner is somebody's work, so it is signed — bottom left, the way the cards sign
     theirs. "Illus." is the same word the card credits use, so it needs no new string. */
  h+='<p class="tla-hero-illus">'+esc(t('ubillus'))+' '
    +'<a href="'+esc(HERO_ART.url)+'" target="_blank" rel="noopener">'+esc(HERO_ART.by)+'</a></p>';
  h+='</div>';
  if(li){h+=verBanner(li);}
  /* A pack whose interface was machine-translated says so, before anything else on the
     page claims authorship. Driven by the string being there, not by a list of language
     codes: a pack translated by a person simply leaves it empty and no notice appears.
     The notice offers three ways to report a mistake, all live: the "mtnotice" string links
     e-mail, GitHub, and the word "Discord" (the same channel the footer's Discord modal opens
     — the two homes for that URL, per the modal's comment in index.html). */
  var mt=t('mtnotice');
  if(mt&&mt!=='mtnotice'){
    h+='<aside class="tla-notice tla-notice-mt" role="note">'
      +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
      +'<path d="M12 3 2 20h20L12 3z"/><path d="M12 9v5M12 17h.01"/></svg>'
      +'<p data-i18n-html="mtnotice">'+mt+'</p></aside>';
  }
  /* …and, right beside it, the other thing this reader most needs to know: the rulebooks
     themselves have not been found in their language. Same place, because the two together are
     the whole answer to "why is this page not in my language?" — and it asks for the PDFs,
     which is the only thing that can actually fix it. */
  if(s.nobook){
    h+='<aside class="tla-notice tla-notice-mt" role="note">'
      +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
      +'<path d="M12 3 2 20h20L12 3z"/><path d="M12 9v5M12 17h.01"/></svg>'
      +'<p data-i18n-html="nobooknotice">'+t('nobooknotice')+'</p></aside>';
  }
  h+=rmPanel();
  /* English leads; the other languages follow. Say so up front, and how to help fill a
     gap. The email is a real mailto link, so it travels with the translated notice. */
  h+='<aside class="tla-notice"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>'
    +'<p data-i18n-html="landingnotice">'+t('landingnotice')+'</p></aside>';
  h+='<h2 class="tla-cards-h">'+esc(t('browse'))+'</h2>';
  h+=flagKeyHTML();
  /* One grid per shelf, each under its own h3. The h2 above still names the whole thing,
     so the outline stays h1 > h2 > h3 with nothing skipped. */
  navGroups().forEach(function(g){
    var items=g.items.filter(function(it){return it.s.kind!=='intro';});
    if(!items.length)return;
    if(g.id)h+='<h3 class="tla-cards-grp" id="cardgrp-'+esc(g.id)+'">'+esc(t('grp'+g.id))+'</h3>';
    h+='<div class="tla-cards"'+(g.id?(' aria-labelledby="cardgrp-'+esc(g.id)+'"'):'')+'>';
    h+=landingCards(items);
    h+='</div>';
  });
  if(s.intro&&s.intro.length){
    h+='<section class="tla-landing-about"><h2>'+esc(t('about'))+'</h2><div class="tla-lead">'+blocksHTML(s.intro)+'</div></section>';
  }
  h+='</div>';
  elMain.innerHTML=h; elToc.innerHTML=''; elMain.scrollTop=0;
}
function landingCards(items){
  var h=''; items.forEach(function(it){
    var s2=it.s, si=it.si;
    var news=s2.kind==='whatsnew';
    var soon=s2.kind==='placeholder';
    var num=news?'<i class="tla-eldersign" aria-hidden="true"></i>':esc(s2.num||'•');
    var meta;
    /* A placeholder says so on its face. It is still a button and still opens: the page
       it opens repeats the promise, which is better than a dead card that ignores a
       click and leaves the reader wondering whether the site is broken. */
    if(soon)meta=t('soon');
    else if(!news)meta=cardMeta(s2);
    else if(s2.ver)meta=t('newver')+' · v'+s2.ver.v;
    else{var ah=langsAhead(lang)[0];
      meta=ah?t('pendingcard').replace('{v}',ah.v).replace('{l}',langName(ah.code)):t('news');}
    var fl=flagOf(s2);
    h+='<button class="tla-card'+(news?' news':'')+(soon?' is-soon':'')+(fl?' has-pennant':'')+'" type="button" data-si="'+si+'">';
    /* The ribbon is text, not decoration: it is the whole point of the flag, so a
       screen reader gets it as part of the card's name rather than a coloured
       shape it cannot see. */
    if(fl)h+='<span class="tla-pennant tla-cardpennant is-'+fl+'">'+esc(t('flag'+fl))+'</span>';
    h+='<span class="tla-card-top"><span class="tla-card-num">'+num+'</span><span class="tla-card-title">'+esc(s2.title)+'</span></span>';
    /* guarded: the card is a flex column with a gap, so an empty span would open a
       phantom row under the title */
    if(meta)h+='<span class="tla-card-meta">'+esc(meta)+'</span>';
    h+='</button>';
  });
  return h;
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
      +(e.role==='subhead'?' class="is-subhead"':'')+'>'+titleFlat(e)+diagBadge(e)+'</a>';
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
  if(sec){sec.classList.add('open');
    /* The shelves start collapsed; open the one holding the active section so it is never
       hidden inside a folded shelf. Others are left as the reader set them. */
    var grp=sec.closest('.tla-navgrp'); if(grp)grp.open=true;
    var b=sec.querySelector('.tla-nav-btn');
    if(b){b.classList.add('active'); b.setAttribute('aria-current','true'); keepInView(b,elNav);}}
}

/* ---------- scroll spy ---------- */
var spyRAF=null;
function spy(){
  if(spyRAF)return; spyRAF=requestAnimationFrame(function(){spyRAF=null;
    var arts=elMain.querySelectorAll('.tla-entry'); var cur=null;
    if(!arts.length){syncHash(null); return;}
    /* Measured against the SCROLLPORT, and against the very rule that parks an entry
       there. getBoundingClientRect() is viewport-relative while an entry is scrolled to
       its own scroll-margin-top from elMain's top edge, so a fixed viewport threshold
       was short by however tall the header is: the entry you just jumped to always
       measured below it and the spy named the one BEFORE it instead. A deep link to
       "…--search" rewrote itself to "…--seal" — you landed right and the URL lied, so
       sharing it or pressing Back sent you somewhere else.
       Reading scroll-margin-top back off the element ties the two together: whatever
       CSS decides is "parked at the top" is what this calls "the one you're reading". */
    var base=elMain.getBoundingClientRect().top;
    var pad=parseFloat(getComputedStyle(arts[0]).scrollMarginTop)||0;
    for(var i=0;i<arts.length;i++){var r=arts[i].getBoundingClientRect();
      if(r.top-base<=pad+40)cur=arts[i].id.slice(2); else break;}
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
function langFlagHTML(L){
  return L.flag?'<img class="tla-flag" src="'+esc(L.flag)+'" alt="" width="20" height="14" aria-hidden="true">':'';
}
/* A row of buttons, one per language, fitted in the header only as long as there are a
   handful. Past that it either wraps over the title or pushes the search off the bar, so the
   current language stays visible and the rest move into a menu behind it — the same disclosure
   the theme picker uses, so there is one keyboard contract in the header and not two.
   The wrapper keeps its .tla-lang class and its group role: the tour points at it by selector,
   and a reader still meets one named group rather than a loose button. */
function buildLangBar(){
  var box=document.querySelector('.tla-lang'); if(!box)return;
  if(LANGS.length<2){box.hidden=true; return;}          // one language: no switcher
  box.hidden=false;
  var cur=regOf(lang)||LANGS[0];
  var rest=LANGS.filter(function(L){return L.code!==cur.code;});
  box.innerHTML=
    '<button type="button" class="tla-lang-cur" id="tla-langcur" aria-expanded="false"'
    +' aria-controls="tla-langmenu" lang="'+esc(cur.code)+'" title="'+esc(t('langgroup'))+'">'
    +langFlagHTML(cur)
    +'<span class="tla-lang-lb">'+esc(cur.label||cur.code.toUpperCase())+'</span>'
    /* The visible label is a two-letter code; the accessible name has to be the language's own
       name, and has to say what the button DOES — otherwise it reads out as "ES, collapsed". */
    +'<span class="tla-sr">'+esc(cur.name)+' — '+esc(t('langgroup'))+'</span>'
    +'<svg class="tla-lang-caret" viewBox="0 0 10 6" aria-hidden="true" focusable="false">'
    +'<path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>'
    +'</button>'
    +'<div class="tla-langmenu" id="tla-langmenu" hidden>'
    +rest.map(function(L){
      return '<button type="button" data-l="'+esc(L.code)+'" lang="'+esc(L.code)+'">'
        +langFlagHTML(L)
        +'<span class="tla-lang-lb">'+esc(L.label||L.code.toUpperCase())+'</span>'
        +'<span class="tla-lang-nm">'+esc(L.name)+'</span></button>';
    }).join('')
    +'</div>';
  // a flag that fails to load would otherwise sit there as an empty framed box
  [].forEach.call(box.querySelectorAll('.tla-flag'),function(img){
    img.addEventListener('error',function(){img.remove();});
  });
}
function langMenuEl(){return document.getElementById('tla-langmenu');}
function langMenuOpen(){var m=langMenuEl(); return !!m&&!m.hidden;}
/* Keep a header dropdown (language / theme) inside the viewport. Both menus are
   position:absolute; right:0 inside their wrapper — correct while the wrapper sits on the
   RIGHT of the header, but on a narrow screen the header wraps and the wrapper can land on
   the LEFT, where right:0 pushes the menu off the left edge and clips the language names.
   Measure on open and, only if it would spill, re-anchor with an explicit left. No-op (no
   inline style) when the default right:0 already fits, so the desktop layout is untouched. */
function clampHeaderMenu(menu, wrap){
  if(!menu||!wrap||menu.hidden)return;
  menu.style.left=''; menu.style.right='';           // restore the CSS default (right:0) before measuring
  var margin=8, wr=wrap.getBoundingClientRect(), mw=menu.offsetWidth, vw=window.innerWidth;
  var vpLeft=wr.right-mw;                             // where right:0 lands the menu's left edge, in viewport coords
  var clamped=Math.max(margin, Math.min(vpLeft, vw-mw-margin));
  if(Math.abs(clamped-vpLeft)>0.5){ menu.style.right='auto'; menu.style.left=(clamped-wr.left)+'px'; }
}
function openLangMenu(){
  var m=langMenuEl(), b=document.getElementById('tla-langcur');
  if(!m||!b)return;
  m.hidden=false; b.setAttribute('aria-expanded','true');
  clampHeaderMenu(m, document.querySelector('.tla-lang'));
  var first=m.querySelector('button'); if(first)first.focus();
}
function closeLangMenu(refocus){
  var m=langMenuEl(), b=document.getElementById('tla-langcur');
  if(!m||!b)return;
  /* Focus FIRST, then hide. Hiding the box while the focus is still inside it drops the focus
     onto the body, and the page then puts it wherever it likes — Escape landed the reader in
     the main region instead of back on the button they opened. Moving it out first means
     nothing is ever focused inside a box that is about to disappear. */
  if(refocus)b.focus();
  m.hidden=true; b.setAttribute('aria-expanded','false');
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
  /* The tour, if it is open, is one of the things written in the old language — and the whole
     point of its language stop is that a reader can change it from there. */
  if(tourOpen())tourRender();
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

/* A cross-reference inside the FAQ chapter 1 that points into the Grimoire crosses a decade
   of rules changes — the two can contradict — so, the first time in a session (until the
   reader opts out), a small dialog names where it leads before following it. Same-corpus
   links and Grimoire links go straight through. */
var xcorpOK=false;
function secById(sid){for(var i=0;i<data.sections.length;i++){if(data.sections[i].id===sid)return data.sections[i];}return null;}
function targetCorpus(eid){var f=findEntry(lang,eid); if(!f)return null; var s=secById(f.sid); return s?(s.corpus||'grimoire'):null;}
/* The Resources viewers (the Ultimatums gallery, the taboo card viewer, …) live in the grimoire
   corpus but are interactive TOOLS, not rules text — a link to them from the FAQ crosses no
   rules-difference, so the cross-corpus guard is skipped for them (see navGuard). */
function targetGroup(eid){var f=findEntry(lang,eid); if(!f)return null; var s=secById(f.sid); return s?(s.group||''):'';}
function targetTitle(eid){var f=findEntry(lang,eid); if(!f)return eid; var s=secById(f.sid); if(!s)return eid;
  if(!f.eid)return s.title;
  for(var j=0;j<(s.entries||[]).length;j++){if(s.entries[j].id===f.eid)return s.entries[j].title;}
  return s.title;}
function navGuard(eid,proceed){
  if(!xcorpOK && curSec && curSec.corpus==='faq1' && targetCorpus(eid)==='grimoire' && targetGroup(eid)!=='resources'){openConfirm(eid,proceed);}
  else proceed();
}
function openConfirm(eid,proceed){
  var prev=document.activeElement;
  var ov=document.createElement('div');
  ov.className='tla-confirm'; ov.setAttribute('role','dialog'); ov.setAttribute('aria-modal','true');
  ov.setAttribute('aria-labelledby','tla-confirm-t'); ov.setAttribute('aria-describedby','tla-confirm-d');
  ov.innerHTML='<div class="tla-confirm-box">'
    +'<h2 class="tla-confirm-t" id="tla-confirm-t">'+esc(t('xcorptitle'))+'</h2>'
    +'<p class="tla-confirm-d" id="tla-confirm-d">'+t('xcorpbody').replace('{t}',esc(targetTitle(eid)))+'</p>'
    +'<label class="tla-confirm-rm"><input type="checkbox" class="tla-confirm-rm-cb"> '+esc(t('xcorpremember'))+'</label>'
    +'<div class="tla-confirm-btns">'
    +'<button type="button" class="tla-confirm-cancel">'+esc(t('cancel'))+'</button>'
    +'<button type="button" class="tla-confirm-ok">'+esc(t('xcorpok'))+' →</button></div></div>';
  (root||document.body).appendChild(ov);
  function close(){document.removeEventListener('keydown',onKey,true); ov.remove(); try{prev&&prev.focus();}catch(e){}}
  function ok(){if(ov.querySelector('.tla-confirm-rm-cb').checked)xcorpOK=true; close(); proceed();}
  function foci(){return [].slice.call(ov.querySelectorAll('button,input'));}
  function onKey(e){
    if(e.key==='Escape'){e.preventDefault(); close(); return;}
    if(e.key==='Tab'){var f=foci(); if(!f.length)return; var i=f.indexOf(document.activeElement);
      if(e.shiftKey){if(i<=0){e.preventDefault(); f[f.length-1].focus();}}
      else{if(i===f.length-1){e.preventDefault(); f[0].focus();}}}
  }
  document.addEventListener('keydown',onKey,true);
  ov.addEventListener('click',function(e){if(e.target===ov)close();});
  ov.querySelector('.tla-confirm-cancel').addEventListener('click',close);
  ov.querySelector('.tla-confirm-ok').addEventListener('click',ok);
  ov.querySelector('.tla-confirm-ok').focus();
}

/* ---- the download bleed chooser (shared by the taboo and UB "download all") ----
   A print bleed is a few extra millimetres of art past the trim, for presses that cut through a
   whole sheet: without it the card must be cut exactly on the line. The chooser explains that once
   and shows the resulting card size both ways — per viewer, since the two use different trims — so
   the reader picks with the real numbers in front of them. The taboo plates carry FFG's own
   measured trim; the UB art is the nominal standard Arkham/poker card. */
var TABOO_TRIM_MM=[62.48,88.73];
var UB_TRIM_MM=[63.5,88.0];
/* One decimal, in the reader's own number format (comma in es/de/it, point in en). */
function fmtMm(n){
  var loc=(PACKS[lang]&&PACKS[lang].locale)||lang;
  try{return n.toLocaleString(loc,{minimumFractionDigits:1,maximumFractionDigits:1});}
  catch(e){return (Math.round(n*10)/10).toFixed(1);}
}
function bleedModal(trim,current,onConfirm){
  var prev=document.activeElement;
  var bw=0.047, bh=0.034;                 // per-edge fraction of W/H; must match addBleed()
  var dims=function(withBleed){
    var w=withBleed?trim[0]*(1+2*bw):trim[0], h=withBleed?trim[1]*(1+2*bh):trim[1];
    return fmtMm(w)+' × '+fmtMm(h)+' mm';
  };
  var opt=function(withBleed,on){
    return '<label class="tla-bleed-opt'+(on?' is-on':'')+'">'
      +'<input type="radio" name="tla-bleed-r" value="'+(withBleed?'1':'0')+'"'+(on?' checked':'')+'>'
      +'<span class="tla-bleed-opt-head"><span class="tla-bleed-opt-name">'+esc(t(withBleed?'tbwithbleed':'tbnobleed'))+'</span>'
      +'<span class="tla-bleed-opt-dim">'+esc(dims(withBleed))+'</span></span>'
      +'<span class="tla-bleed-opt-sub">'+esc(t(withBleed?'tbwithbleedsub':'tbnobleedsub'))+'</span></label>';
  };
  var ov=document.createElement('div');
  ov.className='tla-bleedov'; ov.setAttribute('role','dialog'); ov.setAttribute('aria-modal','true');
  ov.setAttribute('aria-labelledby','tla-bleed-t'); ov.setAttribute('aria-describedby','tla-bleed-d');
  ov.innerHTML='<div class="tla-bleedbox">'
    +'<button type="button" class="tla-bleedclose" aria-label="'+esc(t('close'))+'">&times;</button>'
    +'<h2 class="tla-bleed-t" id="tla-bleed-t">'+esc(t('ubdownall'))+'</h2>'
    +'<p class="tla-bleed-d" id="tla-bleed-d">'+esc(t('tbbleedintro'))+'</p>'
    +'<div class="tla-bleed-opts" role="radiogroup">'+opt(false,!current)+opt(true,!!current)+'</div>'
    +'<div class="tla-bleed-btns"><button type="button" class="tla-bleed-go">'
    +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg> '
    +esc(t('tbbleedgo'))+'</button></div></div>';
  (root||document.body).appendChild(ov);
  function close(){document.removeEventListener('keydown',onKey,true); ov.remove(); try{prev&&prev.focus();}catch(e){}}
  function foci(){return [].slice.call(ov.querySelectorAll('button,input'));}
  function onKey(e){
    if(e.key==='Escape'){e.preventDefault(); close(); return;}
    if(e.key==='Tab'){var f=foci(); if(!f.length)return; var i=f.indexOf(document.activeElement);
      if(e.shiftKey){if(i<=0){e.preventDefault(); f[f.length-1].focus();}}
      else{if(i===f.length-1){e.preventDefault(); f[0].focus();}}}
  }
  function mark(){ [].forEach.call(ov.querySelectorAll('.tla-bleed-opt'),function(l){
    l.classList.toggle('is-on', l.querySelector('input').checked); }); }
  document.addEventListener('keydown',onKey,true);
  ov.addEventListener('change',mark);
  ov.addEventListener('click',function(e){
    if(e.target===ov||e.target.closest('.tla-bleedclose')){close(); return;}
    if(e.target.closest('.tla-bleed-go')){
      var sel=ov.querySelector('input[name="tla-bleed-r"]:checked');
      var bleed=!!(sel&&sel.value==='1'); close(); onConfirm(bleed);
    }
  });
  ov.querySelector('.tla-bleed-go').focus();
}

/* ---------- usage beacon ----------
   Routing happens in the URL #fragment, which the browser never sends, so the
   access log sees every visit as a single request for "/" and cannot say which
   section anyone actually read. One same-origin beacon per navigation closes
   that gap and nothing else: no cookie, no identifier, no third party, no body.
   The PATH is the entire datum and the server answers 204 with nothing, so what
   is recorded is exactly what you can see here in the source.
   Two things that are load-bearing rather than incidental: the section is
   reported by `key` and not by `id`, because ids are translated and the same
   chapter would otherwise split into eleven unrelated rows; and every failure is
   swallowed, because a statistic must never be able to break a page. `sw.js`
   skips /e/ on purpose too — a cached 204 would silence this after the first
   navigation and the numbers would quietly flatline instead of erroring. */
function ping(kind,a,b){
  try{
    var u='/e/'+kind+'/'+encodeURIComponent(a)+(b?'/'+encodeURIComponent(b):'');
    fetch(u,{method:'GET',keepalive:true,cache:'no-store'}).then(null,function(){});
  }catch(e){}
}

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
    /* A filter never survives a navigation — so no URL can ever point at something a
       filter is hiding. That is the whole answer to the deep link
       "#es/juego-orden--i-fase-de-mitos" (a prose entry): were diagOnly sticky, its
       element would not exist, render()'s scroll-to would silently find nothing, and
       the reader would land mid-page on a chapter without the thing they clicked. */
    glossFilter='all'; docView='all'; verOnly=null;
    if(L!==lang||data!==GRIM[L])applyLang(L);
    var f=target?findEntry(L,target):null;
    if(f){render(f.sid,f.eid,lastFlash);} else {render(data.sections[0].id,null,false);}
    lastFlash=false; closeResults();
    /* …but never out of an open dialog: the welcome tour is modal, and a route that ran
       under it would pull focus onto the page the reader cannot reach. */
    if(!firstRoute&&!tourOpen()){try{elMain.focus({preventScroll:true});}catch(e){}} firstRoute=false;
    try{localStorage.setItem('tla-lang',L);}catch(e){}
    /* Reported after render, so it is the section actually shown rather than the
       one the hash asked for — a stale deep link lands on the first chapter, and
       that is what the reader saw. */
    if(curSec)ping('s',L,curSec.key||curSec.id);
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
/* The grimoire (2026) and the FAQ chapter 1 (pre-2026) are two rulesets a decade apart,
   for the same game, and they can contradict each other — so search runs over BOTH at once
   and the results are shown divided, each under its own heading, so a reader comparing
   "what the rule is now" with "what it was" sees both side by side rather than one buried
   under the other. Order and per-corpus cap are fixed here; renderResults draws the split. */
var SEARCH_CORPORA=[{corpus:'grimoire',grp:'grpgrimoire'},{corpus:'faq1',grp:'grpchapter1'}];
var SEARCH_CAP=30;
/* ---------- on-device search history ----------
   Which queries the reader has run and how often — kept in localStorage, never leaves the device.
   The box offers the ones they RETURN to (searched >= SRCH_MIN times), most-used first, so a one-off
   search never clutters it. A search "counts" only when the reader ACTS on it (opens a result or
   presses Enter on one), not on every keystroke. */
var SRCH_KEY='tla-searches', SRCH_VER=2, SRCH_MIN=2, SRCH_MAX=40, SRCH_SHOW=6;
/* Stored as {v, m:{key:{n,t,q}}}. The `v` guards the schema: an older/foreign shape — e.g. the
   pre-release build that saved the TYPED text instead of the chosen result's title — fails the
   check and is dropped, so no one is left staring at stale "esc"/"lug"-style entries. */
function srchLoad(){try{var o=JSON.parse(localStorage.getItem(SRCH_KEY)); if(o&&o.v===SRCH_VER&&o.m&&typeof o.m==='object')return o.m;}catch(e){} return {};}
function srchSave(m){try{localStorage.setItem(SRCH_KEY,JSON.stringify({v:SRCH_VER,m:m}));}catch(e){}}
function recordSearch(q){
  q=String(q||'').trim(); if(q.length<2)return;
  var key=q.toLowerCase(), o=srchLoad(), e=o[key], now=(+new Date());
  if(e){e.n++; e.t=now; e.q=q;} else {o[key]={n:1,t:now,q:q};}
  var ks=Object.keys(o);
  if(ks.length>SRCH_MAX){ks.sort(function(a,b){return o[a].t-o[b].t;}); for(var i=0;i<ks.length-SRCH_MAX;i++)delete o[ks[i]];}
  srchSave(o);
}
function topSearches(){
  var o=srchLoad(), a=[], k; for(k in o){if(o.hasOwnProperty(k)&&o[k]&&o[k].n>=SRCH_MIN)a.push(o[k]);}
  a.sort(function(x,y){return (y.n-x.n)||(y.t-x.t);});
  return a.slice(0,SRCH_SHOW);
}
function clearSearches(){try{localStorage.removeItem(SRCH_KEY);}catch(e){}}
function toggleClear(){if(elSClear)elSClear.hidden=!(elQ.value&&elQ.value.length);}
/* The "most searched" panel, shown in place of results while the box is empty. Items reuse the
   result rows' id sequence (tla-res-N) + role=option, so the same arrow-key navigation and
   aria-activedescendant work over them; a `.tla-sugg` is APPLIED to the box (autocomplete) on
   click/Enter, instead of navigating to a page. */
function suggHTML(){
  var top=topSearches(); if(!top.length)return '';
  var h='<div class="tla-sugg-wrap"><div class="tla-sugg-hd"><span>'+esc(t('mostsearched'))+'</span>'
    +'<button type="button" class="tla-sugg-clear" data-suggclear>'+esc(t('clearhist'))+'</button></div>';
  top.forEach(function(e,i){
    h+='<button type="button" class="tla-sugg" role="option" id="tla-res-'+i+'" data-i="'+i+'" aria-selected="false" data-q="'+esc(e.q)+'">'
      +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>'
      +'<span class="tla-sugg-q">'+esc(e.q)+'</span></button>';
  });
  return h+'</div>';
}
function showSuggestions(){
  var h=suggHTML();
  if(!h){closeResults();return;}
  elRes.innerHTML=h; elRes.classList.add('on'); resSel=-1; clearActiveDesc(); setExpanded(true);
}
function applySugg(q){elQ.value=q; try{elQ.focus();}catch(e){} toggleClear(); search(q);}
function search(q){
  q=norm(q.trim()); if(q.length<2){showSuggestions();return;}
  var terms=q.split(/\s+/), arr=searchIndex[lang], by={};
  for(var i=0;i<arr.length;i++){var it=arr[i]; var hayT=norm(it.title), hayX=norm(it.text);
    var score=0,ok=true;
    for(var ti=0;ti<terms.length;ti++){var tm=terms[ti];
      var inT=hayT.indexOf(tm), inX=hayX.indexOf(tm);
      if(inT<0&&inX<0){ok=false;break;}
      if(inT===0)score+=100; else if(inT>0)score+=40; if(inX>=0)score+=6;
    }
    if(ok){var c=it.corpus||'grimoire'; (by[c]||(by[c]=[])).push({it:it,score:score});}
  }
  var groups=[];
  SEARCH_CORPORA.forEach(function(cg){
    var list=by[cg.corpus]; if(!list||!list.length)return;
    list.sort(function(a,b){return b.score-a.score||a.it.title.length-b.it.title.length;});
    groups.push({label:t(cg.grp),items:list.slice(0,SEARCH_CAP)});
  });
  renderResults(groups,terms);
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
/* `groups` = [{label, items:[{it,score}]}], already split by corpus. The result rows keep
   ONE flat id sequence (tla-res-0, tla-res-1, …) across every group so keyboard navigation
   and aria-activedescendant span the whole list; the group headers are labels, not options,
   so they carry role="presentation" and the listbox is wrapped in role="group" per corpus. */
function renderResults(groups,terms){
  var total=groups.reduce(function(n,g){return n+g.items.length;},0);
  if(!total){elRes.innerHTML='<div class="tla-res-empty">'+esc(t('nores'))+'</div>'; elRes.classList.add('on'); resSel=-1; clearActiveDesc(); setExpanded(true); return;}
  /* Two corpora sit SIDE BY SIDE — the Grimoire (now) on the left, the FAQ chapter 1 (then)
     on the right — so the reader compares them at a glance. One corpus alone is a plain list.
     The option ids stay one flat sequence across both columns, so keyboard nav and
     aria-activedescendant are unaffected by the two-column layout. */
  var h='', i=0, multi=groups.length>1;
  if(multi)h+='<div class="tla-res-cols">';
  groups.forEach(function(g){
    if(multi)h+='<div class="tla-res-col" role="group" aria-label="'+esc(g.label)+'">';
    if(multi)h+='<div class="tla-res-grp" role="presentation">'+esc(g.label)+' <span class="tla-res-grpn">'+g.items.length+'</span></div>';
    g.items.forEach(function(o){var it=o.it;
      h+='<div class="tla-res" role="option" id="tla-res-'+i+'" aria-selected="false" data-eid="'+esc(it.eid)+'" data-title="'+esc(it.title)+'" data-i="'+i+'">';
      /* A real space, not only the CSS gap: this whole row is the option's accessible name,
         so without it a screen reader says "Mazo de EncuentrosI" as one word — and it is
         also what the reader sees if the stylesheet ever fails to load. */
      h+='<div class="rt">'+(it.titleRuns?runsHTML(it.titleRuns):hl(it.title,terms))+' <span class="rs">'+(it.num?it.num+' · ':'')+esc(it.sec)+'</span></div>';
      h+='<div class="rx">'+hl(snippet(it.text,terms),terms)+'</div></div>';
      i++;
    });
    if(multi)h+='</div>';
  });
  if(multi)h+='</div>';
  elRes.innerHTML=h; elRes.classList.add('on'); resSel=-1; clearActiveDesc(); setExpanded(true);
}
/* The options are gone: stop pointing at one, or the attribute names a dead id. */
function clearActiveDesc(){elQ.removeAttribute('aria-activedescendant');}
function closeResults(){elRes.classList.remove('on'); elRes.innerHTML=''; resSel=-1; clearActiveDesc(); setExpanded(false);}
function setExpanded(v){elQ.setAttribute('aria-expanded',v?'true':'false');}
function moveSel(d){var items=elRes.querySelectorAll('.tla-res, .tla-sugg'); if(!items.length)return;
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
  toggleClear();
  if(elQ.value.trim().length>=2)search(elQ.value); else showSuggestions();
}
/* Focus goes back where it came from, not always to the header button: the
   dialog can be opened with '/' from anywhere on the page. */
function closeSearch(){
  elSModal.hidden=true; elQ.value=''; closeResults(); toggleClear();
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
    /* The language menu is the same kind of disclosure as the theme one, and joins the same
       stack for the same reason: one Escape closes one layer, and Tab may leave it. */
    {box:langMenuEl(),isOpen:langMenuOpen,modal:false,
     close:function(){closeLangMenu(true);}},
    {box:elSModal,   isOpen:searchOpen,  close:closeSearch},
    {box:elFigModal, isOpen:figInfoOpen, close:closeFigInfo},
    {box:elDonate,   isOpen:donateOpen,  close:closeDonate},
    {box:elGh,       isOpen:ghOpen,      close:closeGh},
    {box:elDiscord,  isOpen:discordOpen, close:closeDiscord},
    {box:elOffline,  isOpen:offlineOpen, close:closeOffline},
    {box:elUbDraw,   isOpen:drawOpen,    close:closeDraw},
    /* Last, so it wins when opened over another dialog (a drawn card zoomed over the
       draw modal): openDialog() takes the last open entry, and trapTab/Escape follow it. */
    {box:elLb,       isOpen:lbOpen,      close:closeLightbox},
    /* The tour is drawn over everything and is the only thing the reader can act on, so it
       is last of all: Escape leaves it and Tab stays inside its card. */
    {box:elRel,      isOpen:relOpen,     close:closeRelease},
    {box:elTour,     isOpen:tourOpen,    close:tourClose}
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

/* ---------- donate modal ---------- */
/* ---------- release notes ----------
   What changed and when. The site is a living document like the books it carries, so it says
   so out loud. The notes are CONTENT — one entry per release, translated per language — and they
   grow with every ship, so they live in their own file (data/releases.json), fetched on demand
   the first time the panel opens rather than bundled into every pack's ui.json. Shape: a
   newest-first array of {v, date, i18n:{<code>:{title, items}}}. A very small subset of markdown
   is honoured (**bold**); relPick chooses the reader's language with the usual English fallback. */
var elRel=null, lastRel=null, RELEASES=null, releasesReq=null;
/* Visibility is the `on` class, as with every other modal here — `hidden` alone leaves the
   box at display:none, so nothing inside it can take focus. */
function relOpen(){return !!(elRel&&elRel.classList.contains('on'));}
/* Fetched once and cached, so a changelog that grows with every release never weighs on startup;
   the panel shows a busy state until it lands, and falls back to the load-error string if it fails. */
function loadReleases(){
  if(RELEASES)return Promise.resolve(RELEASES);
  if(releasesReq)return releasesReq;
  releasesReq=getJSON('data/releases.json').then(function(r){RELEASES=r||[]; return RELEASES;});
  return releasesReq;
}
function relBold(str){
  /* Escape first, then re-introduce the one tag we allow: nothing from the pack can inject
     markup this way, only ask for emphasis. */
  return esc(str).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
}
/* The reader's language, then down the fallback chain to English — same rule as pick(). Returns
   the chosen {title, items} and the code it came from, so a fallback can be tagged lang="…". */
function relPick(entry){
  var i18n=entry&&entry.i18n; if(!i18n)return null;
  var ch=chainOf(lang);
  for(var i=0;i<ch.length;i++){ if(i18n[ch[i]])return {o:i18n[ch[i]], code:ch[i]}; }
  if(i18n.en)return {o:i18n.en, code:'en'};
  for(var k in i18n){ if(i18n.hasOwnProperty(k))return {o:i18n[k], code:k}; }
  return null;
}
function relNotesHTML(rel){
  rel=rel||[];
  if(!rel.length)return '<p class="tla-modal-p">'+esc(t('soon'))+'</p>';
  var h='';
  rel.forEach(function(r,i){
    /* Each version is a collapsible <details>, collapsed by default and newest first (the file is
       stored newest-first). The summary alone shows the version, its name, the date and a current/old
       tag; opening it reveals the item list. <details>/<summary> is keyboard- and reader-native. */
    var p=relPick(r), o=p?p.o:{}, tag=(p&&p.code!==lang)?(' lang="'+esc(p.code)+'"'):'';
    h+='<details class="tla-rel-item">';
    h+='<summary class="tla-rel-sum">'
      +'<span class="tla-rel-head"><span class="tla-rel-v">'+esc(r.v)+'</span>'
      +(o.title?'<span class="tla-rel-name"'+tag+'>'+esc(o.title)+'</span>':'')+'</span>'
      +'<span class="tla-rel-meta">'+(r.date?esc(fmtDate(r.date)):'')
      +'<span class="'+(i===0?'tla-rel-now':'tla-rel-old')+'">'+esc(t(i===0?'relcurrent':'relold'))+'</span></span>'
      +'</summary>';
    if(o.items&&o.items.length){
      h+='<ul class="tla-rel-list"'+tag+'>';
      o.items.forEach(function(x){h+='<li>'+relBold(x)+'</li>';});
      h+='</ul>';
    }
    h+='</details>';
  });
  return h;
}
function openRelease(){
  lastRel=document.activeElement;
  var body=document.getElementById('tla-rel-body');
  elRel.hidden=false; elRel.classList.add('on');
  var c=document.getElementById('tla-rel-close'); if(c)try{c.focus();}catch(e){}
  if(!body)return;
  /* Already fetched this session -> render now. First time -> a busy state until the file lands. */
  if(RELEASES){ body.removeAttribute('aria-busy'); body.innerHTML=relNotesHTML(RELEASES); return; }
  body.setAttribute('aria-busy','true');
  body.innerHTML='<div class="tla-rel-loading" aria-hidden="true"></div>';
  loadReleases().then(function(rel){
    if(!relOpen())return;               // the reader closed the panel before it arrived
    body.removeAttribute('aria-busy'); body.innerHTML=relNotesHTML(rel);
  },function(){
    body.removeAttribute('aria-busy'); body.innerHTML='<p class="tla-modal-p">'+esc(t('loaderr'))+'</p>';
  });
}
function closeRelease(){
  if(!relOpen())return;
  elRel.classList.remove('on'); elRel.hidden=true;
  var back=(lastRel&&document.contains(lastRel))?lastRel:document.getElementById('tla-rel-open');
  lastRel=null;
  if(back)try{back.focus();}catch(e){}
}

var lastDonate=null;
function donateOpen(){return elDonate.classList.contains('on');}
function openDonate(){
  lastDonate=document.activeElement;
  elDonate.hidden=false; elDonate.classList.add('on');
  try{document.getElementById('tla-donate-close').focus();}catch(e){}
}
function closeDonate(){
  if(!donateOpen())return;
  elDonate.classList.remove('on'); elDonate.hidden=true;
  try{if(lastDonate)lastDonate.focus();}catch(e){}
  lastDonate=null;
}

/* ---------- discord modal ----------
   The same disclosure as the donate one. It is a dialog rather than a plain outbound link
   for one reason: there is no invite URL yet, and this is where the reader is told so — in
   their own language, which a dead link could not do. Once the invite exists this can stay
   exactly as it is; only the markup inside the box changes. */
var lastDiscord=null;
function discordOpen(){return elDiscord.classList.contains('on');}
function openDiscord(){
  lastDiscord=document.activeElement;
  elDiscord.hidden=false; elDiscord.classList.add('on');
  try{document.getElementById('tla-discord-close').focus();}catch(e){}
}
function closeDiscord(){
  if(!discordOpen())return;
  elDiscord.classList.remove('on'); elDiscord.hidden=true;
  try{if(lastDiscord)lastDiscord.focus();}catch(e){}
  lastDiscord=null;
}

/* ---------- contribute modal ----------
   The GitHub mark opens this instead of the repository, because "all the code is on GitHub" is
   the least useful half of the answer: what a would-be contributor needs is which kinds of help
   are wanted and where to start the conversation. The repository link is inside, at the end. */
var lastGh=null;
function ghOpen(){return elGh.classList.contains('on');}
function openGh(){
  lastGh=document.activeElement;
  elGh.hidden=false; elGh.classList.add('on');
  try{document.getElementById('tla-gh-close').focus();}catch(e){}
}
function closeGh(){
  if(!ghOpen())return;
  elGh.classList.remove('on'); elGh.hidden=true;
  try{if(lastGh)lastGh.focus();}catch(e){}
  lastGh=null;
}

/* ---------- use offline (PWA) ----------
   sw.js does the caching; this panel just drives it: install the app, and let the reader keep
   the rules — or everything — offline. It all no-ops without a service worker (the footer icon
   stays hidden), so nothing here can break a browser that does not support it. */
var elOffline=null, lastOffline=null, deferredInstall=null;
function offlineOpen(){return !!elOffline&&elOffline.classList.contains('on');}
function openOffline(){
  lastOffline=document.activeElement;
  elOffline.hidden=false; elOffline.classList.add('on');
  var pr=document.getElementById('tla-offline-prog'); if(pr)pr.hidden=true;      // no stray bar
  var st=document.getElementById('tla-offline-status'); if(st)st.textContent=t('offlinenote');
  try{document.getElementById('tla-offline-close').focus();}catch(e){}
  offlineAskStatus();
}
function closeOffline(){
  if(!offlineOpen())return;
  elOffline.classList.remove('on'); elOffline.hidden=true;
  try{if(lastOffline)lastOffline.focus();}catch(e){}
  lastOffline=null;
}
function offlineSW(){ return ('serviceWorker' in navigator) ? navigator.serviceWorker : null; }
function offlineAskStatus(){ var sw=offlineSW(); if(sw&&sw.controller)sw.controller.postMessage({type:'status'}); }
function offlineMark(id, saved){ var b=document.getElementById(id); if(b)b.classList.toggle('is-saved', !!saved); }
function offlineBusy(on){
  var r=document.getElementById('tla-offline-rules'), a=document.getElementById('tla-offline-all');
  if(r)r.disabled=on; if(a)a.disabled=on;
}
function offlineProgress(done,total){
  var pr=document.getElementById('tla-offline-prog'), bar=document.getElementById('tla-offline-bar'), tx=document.getElementById('tla-offline-progtext');
  if(!pr)return; pr.hidden=false;
  var pct=total?Math.max(0,Math.min(100,Math.round(done/total*100))):0;
  if(bar)bar.style.width=pct+'%';
  if(tx)tx.textContent=t('offlinebusy')+' '+pct+'%';
}
function offlineDownload(what){
  var sw=offlineSW(); if(!sw||!sw.controller)return;
  offlineBusy(true); offlineProgress(0,1);
  sw.controller.postMessage({type:'cache', what:what});
}
function offlineOnMessage(m){
  if(!m||!m.type)return;
  if(m.type==='status'){
    var rulesSaved=m.rules&&m.rules.total>0&&m.rules.have>=m.rules.total;
    var allSaved=rulesSaved&&m.assets&&m.assets.total>0&&m.assets.have>=m.assets.total;
    offlineMark('tla-offline-rules', rulesSaved);
    offlineMark('tla-offline-all', allSaved);
  }else if(m.type==='cache-progress'){
    offlineProgress(m.done, m.total);
  }else if(m.type==='cache-done'){
    var pr=document.getElementById('tla-offline-prog'); if(pr)pr.hidden=true;    // bar gone when done
    var st=document.getElementById('tla-offline-status'); if(st)st.textContent=t('offlinedone');
    offlineBusy(false); offlineAskStatus();
  }
}

/* ---------- draw-at-random modal ---------- */
var lastDraw=null;
function drawOpen(){return elUbDraw.classList.contains('on');}
function openDraw(){
  var s=curSec; if(!s)return;
  lastDraw=document.activeElement;
  /* Labels and caps come from the current section's own buckets, in the reader's
     language — never hardcoded, so a new language and new cards need no code change. */
  var uMax=ubBucket(s,'ultimatum').length, bMax=ubBucket(s,'boon').length;
  var setField=function(labelId,inputId,maxId,label,max){
    var l=document.getElementById(labelId), inp=document.getElementById(inputId), mx=document.getElementById(maxId);
    if(l)l.textContent=label;
    if(inp){inp.max=max; if((parseInt(inp.value,10)||0)>max)inp.value=max;}
    if(mx)mx.textContent=t('ubdrawmax').replace('{n}',max);
  };
  setField('tla-ubdraw-ul','tla-ubdraw-u','tla-ubdraw-umax',ubLabel('ultimatum'),uMax);
  setField('tla-ubdraw-bl','tla-ubdraw-b','tla-ubdraw-bmax',ubLabel('boon'),bMax);
  var out=document.getElementById('tla-ubdraw-out'); if(out)out.innerHTML='';
  elUbDraw.hidden=false; elUbDraw.classList.add('on');
  try{document.getElementById('tla-ubdraw-close').focus();}catch(e){}
}
function closeDraw(){
  if(!drawOpen())return;
  elUbDraw.classList.remove('on'); elUbDraw.hidden=true;
  var out=document.getElementById('tla-ubdraw-out'); if(out)out.innerHTML='';
  try{if(lastDraw)lastDraw.focus();}catch(e){}
  lastDraw=null;
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
/* ---------- the welcome tour ----------
   Six short stops on a first visit: what this is, the language switch (and that English runs
   ahead), the theme, the search, the two rulebooks in the sidebar, and who made it. Written
   here rather than pulled from a tour library because the whole thing is one scrim, one card
   and a rectangle — and a library would have to be loaded, styled and made accessible anyway.

   It is a real modal dialog: focus moves into it, Tab is trapped, Escape leaves, and every stop
   is announced by its own heading. The highlight is a plain box drawn OVER the page (a huge
   spread shadow makes everything else dark), so no element on the page is restyled, re-stacked
   or moved to make room for it. A target that is not on screen — the sidebar on a narrow
   window — simply gets no rectangle, and the stop reads as a centred card. */
/* The language switch rides on the FIRST stop, not on the one that talks about languages: a
   reader who landed in a language they cannot read has to be able to fix that before the
   welcome makes any sense, and the flags say what the sentence cannot. */
var TOUR=[{t:'tour1t',d:'tour1d',langs:true},
          {t:'tour2t',d:'tour2d',sel:'.tla-lang'},
          {t:'tour3t',d:'tour3d',sel:'#tla-theme'},
          {t:'tour4t',d:'tour4d',sel:'#tla-search-open'},
          {t:'tour5t',d:'tour5d',sel:['#tla-nav','#tla-burger']},
          {t:'tour6t',d:'tour6d'}];
var tourAt=-1, elTour=null, lastTour=null;
function tourSeen(){try{return localStorage.getItem('tla-tour')==='done';}catch(e){return true;}}
function tourMark(){try{localStorage.setItem('tla-tour','done');}catch(e){}}
function tourOpen(){return tourAt>=0;}
function tourTarget(step){
  if(!step.sel)return null;
  /* A stop can name several candidates; we point at the first one actually on screen. The
     sidebar stop is #tla-nav on desktop, but on a phone that drawer is folded off-canvas
     (transform:translateX(-100%) + visibility:hidden), so there we fall through to #tla-burger,
     the button that opens it — otherwise the spotlight lands on nothing at x=-300. */
  var sels=typeof step.sel==='string'?[step.sel]:step.sel;
  for(var i=0;i<sels.length;i++){
    var el=document.querySelector(sels[i]);
    if(!el)continue;
    var r=el.getBoundingClientRect();
    /* Visible = has a box, that box is inside the viewport on BOTH axes (the folded drawer keeps
       its width but sits off to the left), and it is not display:none / visibility:hidden. */
    if(!r.width||!r.height)continue;
    if(r.bottom<=0||r.top>=window.innerHeight||r.right<=0||r.left>=window.innerWidth)continue;
    var cs; try{cs=getComputedStyle(el);}catch(e){cs=null;}
    if(cs&&(cs.visibility==='hidden'||cs.display==='none'))continue;
    return r;
  }
  return null;
}
function tourPlace(){
  if(!elTour)return;
  var step=TOUR[tourAt], r=tourTarget(step);
  var hole=elTour.querySelector('.tla-tour-hole'), card=elTour.querySelector('.tla-tour-card');
  var pad=8;
  if(r){
    hole.className='tla-tour-hole';
    hole.style.left=(r.left-pad)+'px'; hole.style.top=(r.top-pad)+'px';
    hole.style.width=(r.width+pad*2)+'px'; hole.style.height=(r.height+pad*2)+'px';
  }else{
    /* A stop with nothing to point at dims the whole screen. The inline geometry of the
       PREVIOUS stop has to be cleared, not just overridden: an inline left/top/width/height
       beats any stylesheet rule, so the full-screen class alone left the shadow painting
       inside the last rectangle — which is why stepping Back, or reaching the last stop,
       showed a page that was barely dimmed at all. */
    hole.className='tla-tour-hole is-full';
    hole.style.left=hole.style.top=hole.style.width=hole.style.height='';
  }
  card.classList.toggle('is-centred',!r);
  if(!r){card.style.left=''; card.style.top=''; return;}
  /* Under the target when there is room, above it when there is not, and BESIDE it when the
     target is too tall for either — which is the sidebar, and the one stop where covering what
     it points at defeats the stop. Always inside the viewport; measured after the card is in
     the DOM, so its real height is used. */
  var cw=card.offsetWidth, ch=card.offsetHeight, m=14;
  var below=r.bottom+pad+m, above=r.top-pad-m-ch;
  var fit=function(v,max){return Math.max(m,Math.min(v,max-m));};
  if(below+ch<=window.innerHeight-m){
    card.style.top=below+'px';
    card.style.left=fit(r.left+r.width/2-cw/2,window.innerWidth-cw)+'px';
  }else if(above>=m){
    card.style.top=above+'px';
    card.style.left=fit(r.left+r.width/2-cw/2,window.innerWidth-cw)+'px';
  }else{
    var side=r.right+pad+m;
    if(side+cw>window.innerWidth-m)side=r.left-pad-m-cw;      // the other side, then
    card.style.left=fit(side,window.innerWidth-cw)+'px';
    card.style.top=fit(r.top,window.innerHeight-ch)+'px';
  }
}
/* The language step carries the switch itself, not just a pointer at it. A reader who landed in
   a language they cannot read is exactly the reader this stop is for, and asking them to reach
   past a modal dialog to fix it would be the one place the tour actively got in the way. */
function tourLangsHTML(){
  if(LANGS.length<2)return '';
  /* tabindex: once the list is long enough to scroll (CSS caps its height), a keyboard user
     must be able to scroll it. The buttons inside are tab stops anyway, so this only matters
     for the box itself — but a scroller that cannot be focused cannot be scrolled without a
     mouse, and this is the one stop a reader may be stuck on. */
  var h='<div class="tla-tour-langs" role="group" tabindex="0" aria-label="'+esc(t('langgroup'))+'">';
  LANGS.forEach(function(L){
    var flag=L.flag?'<img class="tla-flag" src="'+esc(L.flag)+'" alt="" width="20" height="14" aria-hidden="true">':'';
    h+='<button type="button" class="tla-tour-lang" data-tourlang="'+esc(L.code)+'" lang="'+esc(L.code)
      +'" aria-pressed="'+(L.code===lang)+'">'+flag+'<span>'+esc(L.label||L.code.toUpperCase())+'</span>'
      +'<span class="tla-sr">'+esc(L.name)+'</span></button>';
  });
  return h+'</div>';
}
function tourRender(){
  var step=TOUR[tourAt], last=tourAt===TOUR.length-1;
  elTour.querySelector('.tla-tour-step').textContent=t('tourstep').replace('{i}',tourAt+1).replace('{n}',TOUR.length);
  elTour.querySelector('#tla-tour-t').textContent=t(step.t);
  elTour.querySelector('.tla-tour-d').textContent=t(step.d);
  elTour.querySelector('.tla-tour-extra').innerHTML=step.langs?tourLangsHTML():'';
  /* Re-labelled on every render, not once at the start: a language switch inside the tour has
     to change these words too. */
  elTour.querySelector('.tla-tour-skip').textContent=t('tourskip');
  elTour.querySelector('.tla-tour-back').textContent=t('tourback');
  elTour.querySelector('[data-tour="back"]').hidden=tourAt===0;
  elTour.querySelector('[data-tour="next"]').textContent=last?t('tourdone'):t('tournext');
  elTour.querySelector('[data-tour="skip"]').hidden=last;
  tourPlace();
}
function tourGo(i){
  if(i<0)return;
  if(i>=TOUR.length){tourClose(); return;}
  tourAt=i; tourRender();
  var next=elTour.querySelector('[data-tour="next"]');
  if(next)try{next.focus();}catch(e){}
}
function tourStart(){
  if(tourOpen())return;
  lastTour=document.activeElement;
  if(!elTour){
    elTour=document.createElement('div');
    elTour.className='tla-tour'; elTour.id='tla-tour';
    elTour.setAttribute('role','dialog'); elTour.setAttribute('aria-modal','true');
    elTour.setAttribute('aria-labelledby','tla-tour-t');
    elTour.innerHTML='<div class="tla-tour-hole" aria-hidden="true"></div>'
      +'<div class="tla-tour-card" tabindex="-1">'
      +'<p class="tla-tour-step"></p>'
      +'<h2 class="tla-tour-t" id="tla-tour-t"></h2>'
      +'<p class="tla-tour-d"></p>'
      +'<div class="tla-tour-extra"></div>'
      +'<div class="tla-tour-btns">'
      +'<button type="button" class="tla-tour-skip" data-tour="skip"></button>'
      +'<span class="tla-tour-gap"></span>'
      +'<button type="button" class="tla-tour-back" data-tour="back"></button>'
      +'<button type="button" class="tla-tour-next" data-tour="next"></button>'
      +'</div></div>';
    /* Inside #tla-root, not on <body>: the theme's colours are custom properties declared
       ON that element, so a dialog appended outside it renders unthemed — white text on a
       transparent card, which is exactly what the contrast audit caught. */
    root.appendChild(elTour);
    elTour.addEventListener('click',function(e){
      var b=e.target.closest('[data-tour]'); if(!b)return;
      var k=b.getAttribute('data-tour');
      if(k==='skip')tourClose();
      else if(k==='back')tourGo(tourAt-1);
      else tourGo(tourAt+1);
    });
    /* Switching language rebuilds the page under the tour; the tour itself lives outside
       #tla-main so it survives, but its own words have to be said again in the new language. */
    elTour.addEventListener('click',function(e){
      var lb=e.target.closest('[data-tourlang]'); if(!lb)return;
      var code=lb.getAttribute('data-tourlang');
      if(code===lang)return;
      loadLang(code).then(function(){
        var s2=curSec, g=GRIM[code], m=s2&&s2.key&&g.sections.filter(function(x){return x.key===s2.key;})[0];
        setHash(code,(m||g.sections[0]).id,false);
        /* applyLang re-renders the tour once the route lands; just put the focus back on the
           button that was pressed, since re-rendering replaced it. */
        setTimeout(function(){var n=elTour&&elTour.querySelector('[data-tourlang="'+code+'"]'); if(n)n.focus();},60);
      }, fatal);
    });
    window.addEventListener('resize',function(){if(tourOpen())tourPlace();});
  }
  elTour.hidden=false; root.classList.add('tla-tour-on');
  tourGo(0);
}
function tourClose(){
  if(!tourOpen())return;
  tourAt=-1; tourMark();
  if(elTour)elTour.hidden=true;
  root.classList.remove('tla-tour-on');
  if(lastTour&&lastTour.focus)try{lastTour.focus();}catch(e){}
  lastTour=null;
}
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
      /* cssEsc, not CSS.escape: the file guards CSS.escape behind that helper for the
         browsers it supports, and a bare call throws there — dropping this focus move. */
      var again=elMain.querySelector('[data-wnv="'+cssEsc(wnPick)+'"]');
      if(again){try{again.focus();}catch(err){}}
      var wn=data.whatsnew[wnPick];
      /* Count through plural(), so "1 entrada" not "1 entradas": the announce is heard,
         and a mismatched number reads as broken to a screen-reader user. */
      if(wn)announce('v'+wnPick+': '+wn['new'].length+' '+plural('entries',wn['new'].length)+' ('+t('newbadge')+'), '
        +wn.updated.length+' '+plural('entries',wn.updated.length)+' ('+t('updbadge')+')');
      return;
    }
    var wc=e.target.closest('.tla-wncard'); if(wc){gotoTarget(wc.getAttribute('data-eid'),true); return;}
    /* The quick-reference banner scrolls to the download at the foot — an action on this
       page, so a button, not a link, and it never touches the URL. */
    if(e.target.closest('.tla-qrbanner-go')){
      var dl=document.getElementById('qr-download');
      if(dl){dl.scrollIntoView({block:'center'}); var a=dl.querySelector('.tla-dl'); if(a){try{a.focus();}catch(x){}}}
      return;
    }
    if(e.target.closest('.tla-aztoggle')){toggleAz(); return;}
    /* radios: 'change' is the event, and it is bound below — a click here would miss
       the keyboard entirely (arrow keys move a radio group without ever clicking) */
    if(e.target.closest('.tla-diagpick'))return;
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
    /* These two carry a real href, so a modified click is the browser's to handle —
       intercepting it would take "open in a new tab" away from the reader. Only a
       plain left click is ours, and only to add the flash. */
    if(!modClick(e)){
      var x=e.target.closest('.xref'); if(x){e.preventDefault(); var xt=x.getAttribute('data-t'); navGuard(xt,function(){gotoTarget(xt,true);}); return;}
      var a=e.target.closest('.anchor'); if(a){e.preventDefault(); var at=a.getAttribute('href').split('/')[1]; navGuard(at,function(){gotoTarget(at,true);}); return;}
    }
    var mi=e.target.closest('.tla-montage-i'); if(mi){openFigInfo(mi); return;}
    var mimg=e.target.closest('.tla-montage-img'); if(mimg){openLightbox(mimg.src,mimg.alt); return;}
    var img=e.target.closest('.tla-fig img'); if(img){openLightbox(img.src,img.alt);}
  });
  /* 'change', not 'click': arrow keys move a radio group without ever clicking, and a
     click handler would leave the keyboard unable to switch views at all. */
  elMain.addEventListener('change',function(e){
    var r=e.target.closest('.tla-diagpick input[name=tla-diagview]');
    if(r)setDocView(r.value);
    var v=e.target.closest('.tla-verpick input[name=tla-verview]');
    if(v)setVerOnly(v.value);
  });
  elToc.addEventListener('click',function(e){var a=e.target.closest('[data-eid]'); if(a){e.preventDefault(); gotoTarget(a.getAttribute('data-eid'),true);}});
  elRes.addEventListener('click',function(e){
    if(e.target.closest('[data-suggclear]')){clearSearches(); showSuggestions(); return;}
    var s=e.target.closest('.tla-sugg'); if(s){applySugg(s.getAttribute('data-q')); return;}
    var r=e.target.closest('.tla-res'); if(r){recordSearch(r.getAttribute('data-title')); gotoTarget(r.getAttribute('data-eid'),true); closeSearch();}
  });
  if(elSClear)elSClear.addEventListener('click',function(){elQ.value=''; try{elQ.focus();}catch(e){} toggleClear(); showSuggestions();});
  elSOpen.addEventListener('click',openSearch);
  elSCancel.addEventListener('click',closeSearch);
  elSModal.addEventListener('click',function(e){if(e.target===elSModal)closeSearch();});
  elFigClose.addEventListener('click',closeFigInfo);
  elFigModal.addEventListener('click',function(e){if(e.target===elFigModal)closeFigInfo();});
  document.querySelector('.tla-lang').addEventListener('click',function(e){
    var b=e.target.closest('button'); if(!b)return;
    if(b.id==='tla-langcur'){langMenuOpen()?closeLangMenu(true):openLangMenu(); return;}
    var to=b.getAttribute('data-l'); if(to){closeLangMenu(false); setLang(to);}
  });
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
    var lb=document.querySelector('.tla-lang');
    if(langMenuOpen() && lb && !lb.contains(e.target))closeLangMenu(false);
  });
  /* …and tabbing out of it does too, the same as the theme menu: a disclosure left hanging
     behind the reader is a trap for the next Tab press. */
  document.querySelector('.tla-lang').addEventListener('focusout',function(e){
    if(!langMenuOpen())return;
    var to=e.relatedTarget, lb=document.querySelector('.tla-lang');
    if(to && !lb.contains(to))closeLangMenu(false);
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
  elQ.addEventListener('input',function(){toggleClear(); clearTimeout(qTimer); qTimer=setTimeout(function(){qTimer=null; search(elQ.value);},110);});
  elQ.addEventListener('focus',function(){if(elQ.value.trim().length>=2)search(elQ.value);});
  /* No Escape here: the document handler owns it, so that one press closes one
     layer. Handling it here too would close the dialog and then let the same
     press bubble on and dismiss whatever is underneath. */
  elQ.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){e.preventDefault();moveSel(1);}
    else if(e.key==='ArrowUp'){e.preventDefault();moveSel(-1);}
    else if(e.key==='Enter'){e.preventDefault();
      /* Enter can beat the 110ms input debounce: if a search is still pending, run it NOW so the
         results match what's typed, and cancel the timer so it can't fire after we close (which
         left the panel reopening intermittently). No pending timer -> keep the arrow selection. */
      if(qTimer){clearTimeout(qTimer); qTimer=null; search(elQ.value);}
      var items=elRes.querySelectorAll('.tla-res, .tla-sugg'); var chosen=items[resSel<0?0:resSel];
      if(chosen){
        if(chosen.classList.contains('tla-sugg')){applySugg(chosen.getAttribute('data-q'));}
        else {recordSearch(chosen.getAttribute('data-title')); gotoTarget(chosen.getAttribute('data-eid'),true); closeSearch();}
      }}
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
    // a rotate/resize with a header dropdown open moves its wrapper — re-clamp it
    if(langMenuOpen())clampHeaderMenu(langMenuEl(), document.querySelector('.tla-lang'));
    if(themeMenuOpen())clampHeaderMenu(elThemeMenu, elThemeMenu.closest('.tla-themewrap'));
  },{passive:true});

  // clicking the backdrop (or the image) dismisses it, as before — but the
  // close button must not have its own click swallowed by the backdrop rule.
  elLb.addEventListener('click',closeLightbox);

  var tourBtn=document.getElementById('tla-tour-open');
  if(tourBtn)tourBtn.addEventListener('click',function(){tourAt=-1; tourStart();});
  elRel=document.getElementById('tla-rel');
  var relBtn=document.getElementById('tla-rel-open');
  if(relBtn)relBtn.addEventListener('click',openRelease);
  var relX=document.getElementById('tla-rel-close');
  if(relX)relX.addEventListener('click',closeRelease);
  // backdrop only — a click inside the box must not close it
  if(elRel)elRel.addEventListener('click',function(e){if(e.target===elRel)closeRelease();});
  document.getElementById('tla-donate-open').addEventListener('click',openDonate);
  document.getElementById('tla-donate-close').addEventListener('click',closeDonate);
  // backdrop only — a click inside the box must not close it
  elDonate.addEventListener('click',function(e){if(e.target===elDonate)closeDonate();});
  document.getElementById('tla-discord-open').addEventListener('click',openDiscord);
  document.getElementById('tla-discord-close').addEventListener('click',closeDiscord);
  // backdrop only — a click inside the box must not close it
  elDiscord.addEventListener('click',function(e){if(e.target===elDiscord)closeDiscord();});
  document.getElementById('tla-gh-open').addEventListener('click',openGh);
  document.getElementById('tla-gh-close').addEventListener('click',closeGh);
  // backdrop only — a click inside the box must not close it
  elGh.addEventListener('click',function(e){if(e.target===elGh)closeGh();});

  /* PWA "use offline" panel — wired only where the browser can do it, so the footer icon
     (hidden in the markup) is revealed only when it works; everything else no-ops. */
  if('serviceWorker' in navigator){
    elOffline=document.getElementById('tla-offline');
    var offIco=document.getElementById('tla-offline-open');
    if(offIco){ offIco.hidden=false; offIco.addEventListener('click',openOffline); }
    var offX=document.getElementById('tla-offline-close'); if(offX)offX.addEventListener('click',closeOffline);
    if(elOffline)elOffline.addEventListener('click',function(e){if(e.target===elOffline)closeOffline();});
    var offRules=document.getElementById('tla-offline-rules'); if(offRules)offRules.addEventListener('click',function(){offlineDownload('rules');});
    var offAll=document.getElementById('tla-offline-all'); if(offAll)offAll.addEventListener('click',function(){offlineDownload('all');});
    navigator.serviceWorker.addEventListener('message',function(e){offlineOnMessage(e.data);});
    var offInstall=document.getElementById('tla-offline-install');
    if(offInstall)offInstall.addEventListener('click',function(){
      if(!deferredInstall)return;
      try{ deferredInstall.prompt(); deferredInstall.userChoice.then(function(){deferredInstall=null; offInstall.hidden=true;}); }
      catch(e){ deferredInstall=null; offInstall.hidden=true; }
    });
    addEventListener('beforeinstallprompt',function(e){ e.preventDefault(); deferredInstall=e; if(offInstall)offInstall.hidden=false; });
    addEventListener('appinstalled',function(){ deferredInstall=null; if(offInstall)offInstall.hidden=true; });
  }

  document.getElementById('tla-ubdraw-close').addEventListener('click',closeDraw);
  elUbDraw.addEventListener('click',function(e){
    if(e.target===elUbDraw){closeDraw(); return;}
    // the result cards carry their own download button, inside this modal
    var dl=e.target.closest('.tla-ubc-dl'); if(dl){ubDownload(dl.closest('.tla-ubc')); return;}
    // "draw another instead", under each card. Before the zoom check below, and outside
    // .tla-ubc, so pressing it never also enlarges the card it is about to replace.
    var sw=e.target.closest('[data-ubswap]');
    if(sw){var p=sw.getAttribute('data-ubswap').split(':'); ubDrawSwap(+p[0],+p[1]); return;}
    // clicking a drawn card (anywhere but its download button) zooms it
    var card=e.target.closest('.tla-ubdraw-card .tla-ubc'); if(card)ubZoomCard(card);
  });
  document.getElementById('tla-ubdraw-form').addEventListener('submit',function(e){e.preventDefault(); ubDrawRun();});
  /* Live clamp to [0, max]: the field never shows an out-of-range count. The form is
     novalidate (native rangeOverflow would otherwise block submit), so ubDrawRun's own
     clamp is the safety net. */
  ['tla-ubdraw-u','tla-ubdraw-b'].forEach(function(id){
    var inp=document.getElementById(id);
    inp.addEventListener('input',function(){
      var max=parseInt(inp.max,10), v=parseInt(inp.value,10);
      if(inp.value==='')return;
      if(isNaN(v)||v<0)inp.value=0;
      else if(!isNaN(max)&&v>max)inp.value=max;
    });
  });
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

/* Which language's books a book-less one should send its readers to: the one its ui.json
   already falls back to for strings, if that language has a book; else the site's default. */
function bookLangFor(L){
  var chain=chainOf(L);
  for(var i=0;i<chain.length;i++){
    var r=regOf(chain[i]);
    if(r&&r.data)return chain[i];
  }
  var d=regOf(REG&&REG.default);
  if(d&&d.data)return d.code;
  for(var j=0;j<LANGS.length;j++)if(LANGS[j].data)return LANGS[j].code;
  return null;
}
/* The shelf of a language whose rulebooks do not exist in it.

   Same chapters, in the same order, WITH THE SAME IDS as the language they are borrowed from —
   which is what keeps the nav, the contents, the routes and every shared link working, and what
   lets each chapter offer the very same chapter in a language that has it. The content is
   deliberately empty: render() sees `nobook` and says so, in the reader's own words, instead of
   showing prose they were never given. */
function bookShell(src,from,code){
  return {
    lang:code, corpus:src.corpus, versions:[], whatsnew:{}, groupOrder:src.groupOrder,
    groupTitles:src.groupTitles,
    sections:(src.sections||[]).map(function(s){
      /* Don't inherit the source's already-flipped taboo viewer kind: the borrowed shell has no
         cards of its own yet, so it starts as a placeholder and only becomes the viewer if
         attachTabooCards actually loads the English fallback (else a failed fetch would leave an
         empty "taboocards" section beside the nobook notice). */
      return {num:s.num,key:s.key,id:s.id,title:s.title,
              kind:(s.kind==='taboocards'?'placeholder':s.kind),group:s.group,
              corpus:s.corpus,nobook:from,intro:[],entries:[],figures:[]};
    })
  };
}

function loadLang(L){
  // searchIndex is the last thing set, so it is what "fully loaded" means:
  // a load that died half-way must not be mistaken for a finished one.
  if(GRIM[L]&&PACKS[L]&&searchIndex[L])return Promise.resolve(L);
  if(loading[L])return loading[L];
  var reg=regOf(L);
  if(!reg)return Promise.reject(new Error('unknown language: '+L));
  uiTried[L]=true;
  /* A language listed without a data file has its interface translated and no rulebooks (the
     pack declares "uiOnly" — see tools/langpack.py). Its strings are loaded normally; its shelf
     is borrowed, so there is something to navigate and somewhere to send the reader. */
  if(!reg.data){
    loading[L]=getJSON(reg.ui).then(function(u){
      PACKS[L]=u;
      return loadChain(L);
    }).then(function(){
      var src=bookLangFor(L);
      if(!src)throw new Error('no language on this site has a rulebook to borrow');
      return loadLang(src).then(function(){
        GRIM[L]=bookShell(GRIM[src],src,L);
        /* The taboo card viewer is the one section a UI-only language still gets in full: the
           English cards, behind a beta notice. Everything else stays the borrowed shell. */
        return loadTabooCards(reg,L).then(function(tc){
          if(tc)TABOOCARDS[L]=tc;
          attachTabooCards(GRIM[L],TABOOCARDS[L]);
          buildIndex(L);
          delete loading[L];
          return L;
        });
      });
    },function(err){
      delete loading[L]; delete PACKS[L]; delete uiTried[L];
      throw err;
    });
    return loading[L];
  }
  loading[L]=Promise.all([
    GRIM[L]?Promise.resolve(GRIM[L]):getJSON(reg.data),
    PACKS[L]?Promise.resolve(PACKS[L]):getJSON(reg.ui),
    // The FAQ chapter 1 corpus is optional: a language without one (or whose file
    // 404s) simply has no FAQ shelf. Best-effort, never fatal to the language.
    (FAQ[L]||!reg.faqData)?Promise.resolve(FAQ[L]||null)
      :getJSON(reg.faqData).then(function(f){return f;},function(){return null;}),
    // The interactive taboo list is optional too: absent or 404 -> the Resources section keeps
    // its "coming soon" placeholder. Never fatal to the language.
    (TABOO[L]||!reg.tabooData)?Promise.resolve(TABOO[L]||null)
      :getJSON(reg.tabooData).then(function(f){return f;},function(){return null;}),
    /* The Ultimatums viewer's cards, written once for every language (tools/ub_registry.py).
       A card's picture, illustrator and symbols are not translations, so they live in one
       file; the language carries only its name and rule text. Optional and never fatal: an
       older build with no registry simply has the whole record in the language file. */
    UBREG?Promise.resolve(UBREG):getJSON('data/ub.json').then(function(r){return r;},function(){return null;}),
    // The taboo card reprints for the viewer in the Resources section: the language's own, or the
    // English ones with a beta flag. Optional and never fatal (see loadTabooCards / attachTabooCards).
    loadTabooCards(reg, L)
  ]).then(function(res){
    GRIM[L]=res[0]; PACKS[L]=res[1]; if(res[2])FAQ[L]=res[2]; if(res[3])TABOO[L]=res[3];
    if(res[4])UBREG=res[4]; if(res[5])TABOOCARDS[L]=res[5];
    hydrateUB(GRIM[L]);
    return loadChain(L);
  }).then(function(){
    // after the chain, so both may use strings that come from a fallback
    normalizeData(GRIM[L]);
    mergeFaq(GRIM[L], FAQ[L]);          // splice the FAQ corpus in as its own shelf
    attachTaboos(GRIM[L], TABOO[L]);    // hang the taboo list on the Resources section
    attachTabooCards(GRIM[L], TABOOCARDS[L]); // turn the taboos placeholder into the card viewer
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
    /* A first visit gets the tour, once — after the first route, so the header, the sidebar
       and the search button it points at are all on the page to be pointed at. The theme tip
       is the same reader's first second on the site and says the same thing the tour's third
       stop does, so on a first visit the tour speaks and the tip stands down. */
    if(tourSeen())showThemeTip();     // after applyLang: it needs the pack's own words
    else{dropThemeTip(); setTimeout(tourStart,450);}
  }).catch(fatal);
}
boot();
})();
