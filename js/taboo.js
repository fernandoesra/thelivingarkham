/* Draw a taboo card in the browser: the textless picture, then every piece of text over it.

   Written the way js/app.js is written -- an IIFE, no build step, no framework -- so porting it
   into the app is a move rather than a rewrite. The only thing this file knows about the app is
   the icon vocabulary, and that is a table at the top.

   The renderer takes ArkhamDB's markup (its <b>/<i> and its [token] symbols) and turns it into
   real DOM: the symbols become the site's own icon SVGs, drawn through a mask so they take the
   colour of the text around them, exactly as the FAQ chapters draw them. */
(function () {
  'use strict';

  /* ArkhamDB token -> the site's icon name. Almost all of them fold by dropping the underscore;
     [fast] is the exception. The site has drawn that lightning bolt since the FAQ under its older
     name, "free trigger" -- same symbol, older word, so it maps rather than needing a new icon. */
  var ICON = {
    fast: 'free', elder_thing: 'elderthing', elder_sign: 'eldersign',
    auto_fail: 'autofail', per_investigator: 'perinvestigator'
  };

  /* Where this viewer's own assets live: the textless plates, the icon masks, the product marks
     next to a collection number (sets/) and the ones the FAQ prints in a change note (faqsets/).
     The prototype served them from the page root; in the app they sit under assets/taboo/. Kept
     overridable so the same file works in both. */
  var BASE = (typeof window !== 'undefined' && window.TABOO_BASE) || 'assets/taboo/';


  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function iconHTML(token) {
    var name = ICON[token] || token.replace(/_/g, '');
    /* The ico-<name> class carries the glyph's aspect, so the CSS can size it by height and let
       the width follow the shape -- a square box makes every symbol a different size. */
    return '<i class="ico ico-' + esc(name) + '" aria-hidden="true" style="-webkit-mask-image:url(' + BASE + 'icons/'
      + esc(name) + '.svg);mask-image:url(' + BASE + 'icons/' + esc(name) + '.svg)"></i>';
  }

  /* The little product mark the FAQ prints beside a collection number. Not a font glyph: it was
     traced out of the books' vector art and lives as its own SVG named by the shape's
     fingerprint, so it is drawn as a mask exactly as the FAQ chapters draw it. */
  function setHTML(fp) {
    var u = BASE + 'faqsets/' + esc(fp) + '.svg';
    return '<i class="ico ico-set" aria-hidden="true" style="-webkit-mask-image:url(' + u
      + ');mask-image:url(' + u + ')"></i>';
  }

  /* The traits line. ArkhamDB stores it the English way -- "Ally. Miskatonic." -- but the Spanish
     cards do NOT: they set the traits apart with a diamond and drop the closing full stop, "Aliado
     ◆ Miskatonic". So in Spanish the stops become diamonds; every other language keeps FFG's own
     punctuation as printed. */
  function traitsHTML(traits, lang, run) {
    var render = run ? runsHTML : esc;
    if (lang !== 'es' || !traits) return render(traits);
    return String(traits).replace(/[.\s]+$/, '').split(/\.\s+/).map(render)
      .join(' <span class="tbc-tsep" aria-hidden="true">◆</span> ');
  }

  /* One paragraph of ArkhamDB text -> HTML. Five shapes appear and no others -- checked by
     scanning every card, every taboo entry and every flavour line in the list:
       [[Trait]]   a trait named inside the rules; FFG sets these in ArnoPro-BoldItalic,
                   the same face as the traits line itself
       [token]     a symbol, drawn from the site's own icon SVGs
       [set:fp]    a product mark, in the notes that come from the FAQ chapters
       <b> <i>     emphasis
     Everything else is escaped rather than trusted. */
  function runsHTML(text) {
    /* ArkhamDB writes emphasis as <em>/<strong> and an attribution as <cite> in some fields -- the
       flavour, mostly. Lola's back had "<em>The King in Yellow</em>" and the Italian Apripista's
       flavour "<cite>H. P. Lovecraft, ...</cite>" both showed their tags as literal text. Fold
       <em>/<strong> to the <i>/<b> this understands, and drop <cite> (its text stays in the
       flavour's own italic, which is how FFG sets the attribution). */
    text = String(text == null ? '' : text)
      .replace(/<\/?em>/gi, function (t) { return t[1] === '/' ? '</i>' : '<i>'; })
      .replace(/<\/?strong>/gi, function (t) { return t[1] === '/' ? '</b>' : '<b>'; })
      .replace(/<\/?cite>/gi, '');
    var out = '', i = 0, m;
    var re = /\[\[([^\]]+)\]\]|\[set:([a-z0-9-]+)\]|\[([a-z_0-9]+)\]|<(\/?)([bi])>/g;
    while ((m = re.exec(text))) {
      out += esc(text.slice(i, m.index));
      if (m[1]) out += '<b><i>' + esc(m[1]) + '</i></b>';
      else if (m[2]) out += setHTML(m[2]);
      else if (m[3]) out += iconHTML(m[3]);
      else out += '<' + m[4] + m[5] + '>';
      i = re.lastIndex;
    }
    return out + esc(text.slice(i));
  }

  /* The indent of the n-th choice-bullet on a card, as an inline --bulletindent (in cqw, a fraction
     of the card width from the text margin). `c.bulletIndent` is EITHER one number, shared by every
     bullet, OR an ARRAY with a value per bullet in order -- so a card with two bullets can nudge each
     one independently. Absent, or a hole in the array, leaves the ◆ at the margin (its FFG place on
     an asset; an event's ogive then rides it in on its own). Tune it per language in the data file. */
  function bulletInset(c, n) {
    var bi = c && c.bulletIndent;
    var v = bi == null ? null : (typeof bi === 'number' ? bi : bi[n]);
    return (v == null || v === '') ? '' : ' style="--bulletindent:' + esc(v) + 'cqw"';
  }

  /* `lead` is text that joins the FIRST paragraph rather than standing on its own line: FFG runs
     the taboo note straight into the keyword line, printing "Chained (+2 experience). Uses
     (4 ammo)." as one sentence run. Checked against all 94 -- not one prints it on a line of
     its own unless the card has no keyword line at all. */
  function paras(text, cls, lead, c) {
    var list = String(text || '').split(/\n+/).filter(Boolean);
    if (lead) list[0] = list.length ? lead + ' ' + list[0] : lead;
    var bn = 0;
    return list.map(function (p) {
      /* ArkhamDB writes the choices of a "Choose one" ability as lines beginning "- ". FFG sets
         them behind an ornament, hanging in the margin -- the same mark the taboo side already
         draws, so the printed side of a card should not read differently from its taboo side. */
      var bullet = /^-\s+/.test(p);
      if (bullet) p = '[bullet] ' + p.replace(/^-\s+/, '');
      /* A paragraph FFG sets entirely in bold or entirely in italic is centred -- the "card
         designed by" credit, a flavour quotation. The taboo side learns this from the PDF's own
         faces; the printed side comes from ArkhamDB, where the markup is all there is to go on. */
      var whole = p.replace(/\[[a-z_]+\]/g, '').trim();
      var mid = !bullet && (/^<b>[^<]*<\/b>\.?$/.test(whole) || /^<i>[^<]*<\/i>\.?$/.test(whole));
      return '<p class="' + cls + (bullet ? ' tbc-bullet' : mid ? ' tbc-mid' : '') + '"'
        + (bullet ? bulletInset(c, bn++) : '') + '>' + runsHTML(p) + '</p>';
    }).join('');
  }

  /* The taboo note FFG prints on the card, under the traits: "Chained (+2 experience).",
     "Mutated." or "Forbidden." The wording comes from the PDF, which is the authority; the
     ArkhamDB category only decides which of them applies. */
  function tabooNote(c) {
    var t = c.taboo || {};
    if (t.deck_limit === 0) return 'Forbidden.';
    /* FFG prints a true en dash on the unchained cards -- "Unchained (-2 experience)." with a
       plain hyphen is a different glyph and reads narrower than the printed card. */
    if (typeof t.xp === 'number') {
      return (t.xp > 0 ? 'Chained (+' + t.xp + ' experience).'
                       : 'Unchained (–' + Math.abs(t.xp) + ' experience).');
    }
    return t.text ? 'Mutated.' : '';
  }

  /* The taboo bucket a card is in: chained/unchained share one, then mutated, then forbidden. The
     record carries it as `cat`; the fall-back reads it off the taboo record for a card the chapter
     never named. Kept in step with index.html's category(). */
  function taboCat(c) {
    if (c.cat) return c.cat;
    var t = c.taboo || {};
    if (t.deck_limit === 0) return 'forbidden';
    if (typeof t.xp === 'number' && !t.text) return 'chained';
    return 'mutated';
  }

  /* The taboo mark FFG's own cards do not carry but ArkhamDB adds: a chaos-token symbol to the
     right of the name of any card on the list. Ours goes further -- the symbol and its colour say
     WHICH kind of taboo it is: the cultist in green for chained/unchained, the tablet in purple
     for mutated, the auto-fail in red for forbidden. Absolutely placed at the right of the name
     box so a centred name stays centred. */
  var TABMARK = { chained: 'cultist', mutated: 'tablet', forbidden: 'autofail' };
  function tabmark(c) {
    var cat = taboCat(c);
    var sym = TABMARK[cat];
    if (!sym) return '';
    return '<i class="ico ico-' + sym + ' tbc-tabmark tabmark-' + cat + '" aria-hidden="true"'
      + ' style="-webkit-mask-image:url(' + BASE + 'icons/' + sym + '.svg);mask-image:url(' + BASE + 'icons/' + sym
      + '.svg)"></i>';
  }

  /* `taboo` true draws the card as the taboo list changes it; false draws it as printed. */
  function cardHTML(c, taboo) {
    var h = '<div class="tbc" data-type="' + esc(c.type) + '" data-code="' + esc(c.code)
      + '" data-faction="' + esc(c.faction || '')
      + '" data-lang="' + esc(c.lang || 'en') + '">';
    h += '<img class="tbc-pic" src="' + BASE + 'plates/' + esc(c.code) + '.webp" width="' + c.w
      + '" height="' + c.h + '" alt="" draggable="false">';

    /* A permanent asset has no resource cost, and ArkhamDB simply leaves the field out. FFG does
       not leave the circle empty: it prints an em dash, in Teutonic at the same size as a
       numeral. Five of the 94 are like this. */
    /* ArkhamDB has no field for "X": it writes the cost as -2, which the Flute of the Outer Gods
       was printing on its crown as a minus two. Nothing else on any card ever costs a negative. */
    var cost = c.cost != null && c.type !== 'treachery' && c.type !== 'enemy'
      ? (c.cost === -2 ? 'X' : String(c.cost))
      : (c.type === 'asset' || c.type === 'event' ? '—' : null);
    if (cost !== null) h += '<div class="tbc-l tbc-cost">' + esc(cost) + '</div>';

    /* An investigator prints its four skills as figures across the top of the right-hand panel,
       right-aligned -- the '1' of a card like Mandy Thompson is far narrower than a '3', and FFG
       lines their right edges up, not their centres. */
    if (c.stats) {
      h += c.stats.map(function (v, i) {
        return '<div class="tbc-l tbc-skill tbc-skill' + i + '">' + esc(v) + '</div>';
      }).join('');
    }

    /* Health and sanity, in Bolton -- verified rather than assumed: the subset embedded in the
       PDF was extracted and its digit outlines compared with the repo's faces, and all eight
       matched Bolton Regular exactly. White figures with a coloured rim, the rim painted behind
       the fill so it does not eat into the glyph. */
    if (c.health != null || c.sanity != null) {
      /* A card with only one of the two still prints both shields, the empty one carrying a dash
         -- a hand-drawn glyph in FFG's symbol font that the site does not have yet. */
      var stat = function (v, cls) {
        return '<div class="tbc-l tbc-stat ' + cls + '">'
          + (v == null ? iconHTML('novalue') : esc(v)) + '</div>';
      };
      h += stat(c.health, 'tbc-health') + stat(c.sanity, 'tbc-sanity');
    }
    /* One span inside the flex box, not two items plus whitespace: a flex container drops
       whitespace-only children, which would weld the unique mark onto the first letter. */
    /* No space character after the unique mark -- the gap is the margin on the icon and nothing
       else. Having both made the whole name 5% wider than the printed one, which pushed the mark
       out to the left once the line was centred. FFG's own gap between the mark and the first
       letter measures zero: their glyph carries its own advance. */
    /* Our home-made taboo mark (cultist/tablet/autofail by category) belongs ONLY on the taboo
       face; the printed face is exactly as FFG prints it and must not carry our marker. The unique
       bullet stays on both — that one IS FFG's own. */
    h += '<h3 class="tbc-l tbc-name"><span>' + (c.unique ? iconHTML('unique') : '')
      + esc(c.name) + '</span>' + (taboo ? tabmark(c) : '') + '</h3>';
    if (c.subname) h += '<div class="tbc-l tbc-sub">' + esc(c.subname) + '</div>';
    /* A treachery does not carry its type on the little trapezoid under a cost crown -- it has no
       cost at all. It prints TREACHERY on a band above the name, and a weakness prints WEAKNESS
       on a second band below it. */
    if (c.type === 'treachery' || c.type === 'enemy') {
      h += '<div class="tbc-l tbc-band tbc-band-type">' + esc(c.typeName) + '</div>';
      if (c.subtypeName) {
        h += '<div class="tbc-l tbc-band tbc-band-sub">' + esc(c.subtypeName) + '</div>';
      }
    } else if (c.typeName) {
      h += '<div class="tbc-l tbc-type">' + esc(c.typeName) + '</div>';
    }

    /* Two shaped floats, full height, one per side. The text field of an event or a skill card is
       an ogive, not a rectangle: it closes in over the last third, and a rectangular box let the
       final lines run across the curved border. They carry no content and are hidden from the
       accessibility tree -- they exist only to bend the text flow. */
    var body = '<span class="tbc-shape tbc-shape-l" aria-hidden="true"></span>'
      + '<span class="tbc-shape tbc-shape-r" aria-hidden="true"></span>';
    /* The two sides come from different places, and they have to. ArkhamDB stores the card as
       PRINTED, and for a taboo card only prose describing the change -- never the resulting text.
       So the taboo side is FFG's own typesetting, lifted from their PDF: it carries the rewrite
       (Banish's four chaos symbols became one word), the note in the place FFG puts it, and no
       flavour quotation, because a taboo card does not reprint one. */
    if (taboo && c.pdf && c.pdf.paras && c.pdf.paras.length) {
      if (c.pdf.traits) body += '<p class="tbc-traits">' + traitsHTML(c.pdf.traits, c.lang, true) + '</p>';
      /* Each paragraph carries how FFG set it: the rules run to the left margin, the flavour
         quotation and the "card design by" credit are centred. */
      /* FFG opens a taboo card with its list line. On their own reprint the line is already part
         of the first paragraph; on a face we rebuilt it comes separately, because the words are
         the site's own and not FFG's. Either way it is printed once. */
      var lead = c.pdf.note && c.pdf.paras[0]
        && runsHTML(c.pdf.paras[0].t).indexOf(esc(c.pdf.note)) !== 0 ? c.pdf.note : '';
      /* Where the list line goes matches FFG's own English reprint, CARD BY CARD -- not by category.
         FFG mixes both layouts within every bucket: most chained cards set "Chained (+2 experience)."
         on a line of its own, but six run it into a "Fast."/"Play only" keyword line; most mutated
         cards run "Mutated." into the first rule, but twenty-six set it on its own line; Burn After
         Reading sets "Forbidden." alone while the other two forbidden cards run it in. So the build
         reads, per card, whether the ENGLISH face put the note on its own line (its paras[0] IS the
         note) and stamps c.noteOwnLine; English gets its layout for free (the note is already in its
         paragraphs, so lead is empty here), and the rebuilt languages break or run the note to match. */
      var ownLine = lead && c.noteOwnLine;
      if (ownLine) body += '<p class="tbc-p">' + runsHTML(lead) + '</p>';
      var bn = 0;
      body += c.pdf.paras.map(function (p, i) {
        var cls = 'tbc-p' + (p.k === 'flav' ? ' tbc-flav' : p.k === 'center' ? ' tbc-mid'
          : p.k === 'bullet' ? ' tbc-bullet' : '');
        var t = (i === 0 && lead && !ownLine && p.k !== 'bullet' ? lead + ' ' : '') + p.t;
        return '<p class="' + cls + '"' + (p.k === 'bullet' ? bulletInset(c, bn++) : '') + '>'
          + runsHTML(t) + '</p>';
      }).join('');
    } else {
      if (c.traits) body += '<p class="tbc-traits">' + traitsHTML(c.traits, c.lang, false) + '</p>';
      body += paras(c.text, 'tbc-p', taboo ? tabooNote(c) : '', c);
      if (c.flavour && !taboo) body += '<p class="tbc-flav">' + runsHTML(c.flavour) + '</p>';
      /* Victory points. ArkhamDB keeps them in their own field, OUT of the rules text, so a printed
         face built from that text drops the "Victory N." FFG prints under the flavour (Delve Too
         Deep). Take FFG's own wording for it from the taboo face -- the PDF, already in this
         language -- and print it here too, centred and bold as FFG sets it. */
      if (!taboo && c.victory != null && c.pdf && c.pdf.paras) {
        var vic = c.pdf.paras.filter(function (p) {
          return /(victory|victoria|sieg|vittoria)/i.test(p.t);
        }).pop();
        if (vic) body += '<p class="tbc-p tbc-mid">' + runsHTML(vic.t) + '</p>';
      }
    }
    h += '<div class="tbc-l tbc-body">' + body + '</div>';

    h += '<div class="tbc-l tbc-foot tbc-illus">Illus. ' + esc(c.illustrator) + '</div>';
    if (c.copyright) {
      h += '<div class="tbc-l tbc-foot tbc-copy">' + esc(c.copyright) + '</div>';
    }
    /* The product's symbol goes inside the number's box, so it stays glued to its left however
       many digits the number has -- FFG right-aligns the pair, not the number alone. */
    var mark = c.set
      ? '<span class="tbc-set" aria-hidden="true" style="--ia:' + (c.setAspect || 1)
        + ';-webkit-mask-image:url(' + BASE + 'sets/' + esc(c.set) + '.svg);mask-image:url(' + BASE + 'sets/'
        + esc(c.set) + '.svg)"></span>'
      : '';
    h += '<div class="tbc-l tbc-foot tbc-num">' + mark + esc(c.position) + '</div>';
    return h + '</div>';
  }

  /* Shrink text that would overflow its box until it fits. Both the box and the font scale with
     the card's width, so the ratio found here holds at every display size.

     The slack has to be a share of the font size, not a fixed pixel count. Card faces set tight
     leading (FFG uses less than one), so the glyphs of the last line always poke a little below
     the box and scrollHeight always exceeds clientHeight by a hair. That hair grows with the card:
     a fixed 1px tolerance passed at 460px wide and failed at 750px, which shrank the name on a
     wide screen and not on a narrow one -- the same card rendering differently by window size. */
  /* The vertical slack is for descenders hanging out of a tight line box; sideways there is no
     such thing, and letting a word run 0.3em past its box hid the last letter of SUPPORTO on the
     Italian plaque. So width is judged tightly and height is not. */
  /* `vtol` is the vertical slack allowed, as a share of the font size; the default (+0.06) forgives
     the descender hair a tight line box lets poke below its box. */
  function fit(el, prop, lo, vtol) {
    /* Skip an element with no box: the filter hides non-matching cards with `hidden` (display:none),
       and a hidden element reports scrollHeight === clientHeight === 0, which "fits" at any size --
       so measuring it would stamp --fit back to 1 (unshrunk), and the card would then appear HUGE and
       clipped the instant the filter reveals it again. Leaving it untouched keeps the size it was
       fitted to while visible. */
    if (!el || !el.clientHeight) return;
    var set = function (f) { el.style.setProperty(prop, f); };
    var top = 1, vt = vtol == null ? 0.06 : vtol;
    var fits = function () {
      var em = parseFloat(getComputedStyle(el).fontSize);
      return el.scrollHeight <= el.clientHeight + em * vt
        && el.scrollWidth <= el.clientWidth + 0.5;
    };
    set(top);
    if (fits()) return;
    var hi = top, best = lo;
    for (var i = 0; i < 8; i++) {
      var m = (lo + hi) / 2;
      set(m);
      if (fits()) { best = m; lo = m; } else { hi = m; }
    }
    set(best);
  }

  /* The floor is a backstop against squeezing forever, not a style choice. FFG's own smallest
     setting in the taboo PDF is 7.27pt against a 8.5pt base (0.855), but that only bounds the
     cards they reprinted: the ORIGINAL side of a customizable card (Empirical Hypothesis,
     Underworld Market) carries more text than the taboo version, which rewrote it shorter. Those
     genuinely need about 0.75, so the floor sits below them and anything that still will not fit
     is a real signal rather than a card to shrink harder. */
  /* FFG sets a card's rules at one of TWO sizes, 8.5pt or 7.5pt -- 41 of the 90 at the first, 35
     at the second -- and WHICH one is editorial, not mechanical: cards they set small would have
     fitted large, and by character count the two groups overlap almost completely (20 of the 23
     large assets carry more text than the smallest of the small ones). It cannot be derived.

     Reproducing the shape of the choice was tried -- keep the large size while the block sits
     comfortably inside the box, step down when it fills up -- and it works, except that any
     threshold leaves some card sitting exactly on it, and that card then takes one size at 420 px
     wide and the other at 640. A reader would see different type on a phone than on a desktop,
     which is the very fault that took a day to find and fix once already.

     So the base is FFG's SMALLER setting, and the fit only ever shrinks from there. Nothing is
     ever larger than the printed card, and nothing depends on the window. The cost is that the
     airier cards read a little smaller than FFG sets them; that is a visible, deliberate trade
     rather than a moving target. */
  /* Where the flavour and the victory line sit. FFG does not stack them under the rules text: it
     pins "Victory N." to the very BOTTOM of the box, and floats the flavour quotation in the space
     between the end of the rules and whatever is under it (the victory line, or the box floor). So
     after the rules are fitted, the slack left in the box is shared out -- half above the flavour,
     centring it in the gap, and half above the victory, dropping it to the floor. Cards with no
     flavour (every taboo face, and rules-only printed cards) are left exactly as they were. */
  function distributeTail(body) {
    if (!body) return;
    var flav = body.querySelector('.tbc-flav');
    if (!flav) return;
    var vic = flav.nextElementSibling && flav.nextElementSibling.classList.contains('tbc-mid')
      ? flav.nextElementSibling : null;
    flav.style.marginTop = ''; if (vic) vic.style.marginTop = '';
    /* The real gap: how far the last line sits above the box floor. scrollHeight is no use here --
       it never drops below clientHeight -- so this reads the box floor against the last line's box. */
    var last = vic || flav;
    var slack = body.getBoundingClientRect().bottom - last.getBoundingClientRect().bottom;
    if (slack <= 1) return;
    var base = function (el) { return parseFloat(getComputedStyle(el).marginTop) || 0; };
    flav.style.marginTop = (base(flav) + slack / 2) + 'px';
    if (vic) vic.style.marginTop = (base(vic) + slack / 2) + 'px';
  }

  function fitCard(card) {
    /* The floor is a backstop, not a style: 0.79 of the base is 3.34cqw, just under the smallest
       thing FFG prints IN ENGLISH. Only the customizable cards, whose ORIGINAL side carries far
       more text than the taboo rewrite, ever reach it.

       German and Italian say the same rule in more words -- Das Necronomicon runs a fifth longer
       than its English text -- and FFG's own printing of those cards is set smaller to match. So
       the floor travels with the language rather than holding an English number over a German
       card and letting the last line hang out of the box. */
    var en = (card.dataset.lang || 'en') === 'en';
    fit(card.querySelector('.tbc-body'), '--fit', en ? 0.79 : 0.72);
    distributeTail(card.querySelector('.tbc-body'));
    /* a back has no .tbc-name -- its name sits on the bar at the top right, in its own box */
    fit(card.querySelector('.tbc-name,.tbc-bname'), '--namefit', 0.6);
    fit(card.querySelector('.tbc-sub,.tbc-bsub'), '--subfit', 0.6);
    /* The type word and the two treachery bands sit on fixed pieces of art, and the word that
       fits in English does not fit anywhere else: ASSET is five letters, SUPPORTO is eight and
       FERTIGKEIT is ten. The floor is low on purpose -- FFG's own German cards set that word
       small, because the plaque is the same piece of art in every language. */
    fit(card.querySelector('.tbc-type'), '--typefit', 0.45);
    [].forEach.call(card.querySelectorAll('.tbc-band'), function (b) {
      fit(b, '--bandfit', 0.45);
    });
  }

  /* An investigator's BACK: deck-building, not an ability. Its own layout -- the name sits on a
     bar at the top right, and the text wraps around the photograph pinned to the top left, so its
     left margin starts around a third of the way across and drops to the page edge once past the
     picture. For Lola Hayes and Mandy Thompson this is where the taboo change actually is. */
  /* A back's card-space measurements come in as percentages of the card: sideways ones of its
     long side (a cqw, since the card is landscape and the container measures the long side) and
     up-and-down ones of its short side. Turning one into the other is just the card's shape. */
  var LONG_OVER_SHORT = 88.73 / 62.48;
  var BACK_BOTTOM = 92;      // .tbc-bbody's foot, kept level with the CSS
  var BACK_RIGHT = 94.6;

  /* Where the text block starts. FFG reports the top of the first line's FONT box; a CSS line box
     at line-height 1 sits inside that box, half the difference down on each side. */
  function blockTop(b) {
    var em = (b.size || 2.981) * LONG_OVER_SHORT;    // one em, as a share of the card's height
    return b.top + 0.125 * em;
  }

  /* The photograph as an exclusion, traced from FFG's own left margin line by line. The float is
     made exactly as wide as the widest point of the outline, so every x in the polygon lands
     between 0 and 100 of its own box and nothing depends on a width set in the stylesheet. */
  function photoShape(b, top) {
    var pts = b.photo;
    if (!pts || !pts.length) return '';
    var x0 = b.left, w = BACK_RIGHT - b.left, h = BACK_BOTTOM - top;
    var wide = Math.max.apply(null, pts.map(function (p) { return (p[1] - x0) / w * 100; }));
    if (wide <= 0) return '';
    var xy = pts.map(function (p) {
      return ((p[1] - x0) / w * 100 / wide * 100).toFixed(2) + '% '
        + Math.max(0, (p[0] - top) / h * 100).toFixed(2) + '%';
    });
    var last = Math.max(0, (pts[pts.length - 1][0] - top) / h * 100).toFixed(2);
    return 'width:' + wide.toFixed(2) + '%;shape-outside:polygon(0% 0%,'
      + xy.join(',') + ',0% ' + last + '%)';
  }

  /* `back` picks which of an investigator's two backs to draw: the printed one (c.back) or, for
     Lola Hayes and Mandy Thompson whose taboo change is on the back, the modified one
     (c.backTaboo). Both sit on the same textless plate -- only the DOM text differs. */
  function backHTML(c, back) {
    var b = back || c.back;
    if (!b) return '';
    var h = '<div class="tbc tbc-back" data-type="investigator-back" data-code="' + esc(c.code)
      + '" data-lang="' + esc(c.lang || 'en') + '">';
    h += '<img class="tbc-pic" src="' + BASE + 'plates/' + esc(c.code) + '-back.webp" width="1048" height="738"'
      + ' alt="" draggable="false">';
    if (b.name) h += '<h3 class="tbc-l tbc-bname"><span>' + runsHTML(b.name) + '</span>'
      + tabmark(c) + '</h3>';
    if (b.subtitle) h += '<div class="tbc-l tbc-bsub">' + esc(b.subtitle) + '</div>';
    var top = blockTop(b);
    var shape = photoShape(b, top);
    var body = '<span class="tbc-shape tbc-shape-photo" aria-hidden="true"'
      + (shape ? ' style="' + shape + '"' : '') + '></span>';
    body += (b.paras || []).map(function (p) {
      return '<p class="tbc-p">' + runsHTML(p) + '</p>';
    }).join('');
    /* Trish's flavour is set smaller than her rules text, so it carries its own size. */
    if (b.flavour) {
      var fs = b.flavSize && b.flavSize !== b.size
        ? ' style="font-size:calc(var(--fit,1)*' + b.flavSize + 'cqw)"' : '';
      body += '<p class="tbc-p tbc-flav"' + fs + '>' + runsHTML(b.flavour) + '</p>';
    }
    /* The gap between paragraphs travels in cqw, not in ems: FFG opens it to fill the card -- Rex
       gets two thirds more air than Mandy -- and the flavour paragraph may be set at another size,
       so an em would mean something different there than in the block above it. */
    h += '<div class="tbc-l tbc-body tbc-bbody" style="top:' + top.toFixed(2) + '%;left:'
      + b.left + '%;font-size:calc(var(--fit,1)*' + (b.size || 2.981) + 'cqw)'
      + (b.lead ? ';line-height:' + b.lead : '')
      + (b.gap ? ';--bgap:' + (b.gap * b.size).toFixed(3) : '') + '">'
      + body + '</div>';
    return h + '</div>';
  }

  /* The faces the card draws in, as document.fonts.load() specs. Loaded before the auto-fit
     measures, so it sizes to the real metrics and not Georgia's. Mirrors app.js's TAB_FONT_SPECS
     (the downloader waits on the same set); keep the two in step. */
  var FIT_FONT_SPECS = ['40px ubtitle', '40px ubbody', '700 40px ubbody', 'italic 40px ubbody',
    'italic 700 40px ubbody', '40px bolton'];

  window.TabooCard = {
    html: cardHTML,
    back: backHTML,
    /* Exposed so the change note outside the card draws its symbols the same way the card does,
       instead of printing [action] and [fast] as literal text. */
    runs: runsHTML,
    /* The auto-fit has to measure with the real faces, not the fallback, or every card is sized
       for Georgia and then re-drawn wider in ubbody: the block grows and the last line -- a
       "Victory N." -- drops out of the clipped box. document.fonts.ready is NOT enough on its own.
       By the time a reader opens this section the page's OTHER fonts have already settled it, so it
       is an already-resolved promise whose .then fires on the next microtask -- before the card
       faces, referenced here for the first time, have finished loading. So load those exact faces
       first and fit after; fit() forces a layout as it measures, so it then reads the real metrics. */
    fitAll: function (root) {
      var scope = root || document;
      var run = function () {
        [].forEach.call(scope.querySelectorAll('.tbc'), fitCard);
      };
      var spills = function (body) {
        var em = parseFloat(getComputedStyle(body).fontSize);
        return body.scrollHeight > body.clientHeight + em * 0.06 || body.scrollWidth > body.clientWidth + 0.5;
      };
      /* Settling the fit is two jobs, and fit() alone is not reliable enough for either while faces
         are still applying to layout. A face loads, then reflows the text a frame or more later --
         with a still plateau BEFORE it applies -- and a fit measured across that reflow reads a stale
         wrap: a flavour that momentarily sits on one line keeps the larger size, then drops to two and
         spills the clipped box, stuck, because the height is now stable at the wrong value. So:
           - GROW every card to the real metrics a few times as they apply, for FFG's sizing; and
           - every frame, SHRINK anything that is spilling and keep at it -- no guess at "settled by
             now": a spill just keeps getting re-fit until one pass lands while the page is at rest and
             the size sticks (a hand re-fit once settled always sizes it right). Exit after a stretch
             with nothing spilling, or a hard frame cap. Each idle frame is one cheap read. */
      var settle = function () {
        var grow = { 6: 1, 15: 1, 32: 1, 66: 1, 130: 1 };   // ~0.1 / 0.25 / 0.5 / 1.1 / 2.2 s
        var frames = 0, clear = 0;
        var loop = function () {
          if (grow[frames]) run();
          var spill = false;
          [].forEach.call(scope.querySelectorAll('.tbc'), function (card) {
            var body = card.querySelector('.tbc-body');
            if (body && spills(body)) { fitCard(card); spill = true; }
          });
          clear = spill ? 0 : clear + 1;
          if (++frames < 360 && clear < 30 && window.requestAnimationFrame) requestAnimationFrame(loop);
        };
        loop();
      };
      run();                                    // instant, best-effort (may still be the fallback)
      var d = window.document && document.fonts;
      if (d && d.load) {
        Promise.all(FIT_FONT_SPECS.map(function (f) { return d.load(f).catch(function () {}); }))
          .then(function () { return d.ready; })
          .then(settle).catch(function () {});   // authoritative: real faces loaded AND applied
      } else if (d && d.ready) {
        d.ready.then(settle);
      }
    }
  };
})();
