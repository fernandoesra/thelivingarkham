# Deploying

The site is **plain static files**. No build step on the server, no runtime, no database, no API
keys, and nothing to fetch from anywhere else at run time — the ArkhamDB data is baked in when
the content is built, and ArkhamDB itself is only ever an outbound link. Copy the files onto a
web server and you are done.

The only hard requirement is that it is served over **http(s)**, not opened from disk: the app
fetches `data/*.json`, and browsers block `fetch()` on `file://`.

## 1. What to upload

| Upload | Why |
|---|---|
| `index.html` | the page |
| `css/` `js/` | the app |
| `data/` | the built rules (`grimoire_*.json`, `faq_*.json`, `taboos_*.json`, `languages.json`) |
| `assets/` | icons, figures, card art, fonts |
| `langs/<code>/ui.json`, `langs/<code>/flag.svg` | the interface strings and flag of each language |

Everything else is for **building** the content, not for serving it:

| Leave out | Size | What it is |
|---|---|---|
| `langs/*/source/`, `langs/*/source_faq/` | **155 MB** | the source PDFs the pipeline reads |
| `tools/` | — | the Python pipeline |
| `server.js`, `package.json` | — | the local dev server |
| `README.md`, `deploy.md` | — | docs |
| `assets/templates/` | ~1 GB | design sources; git-ignored, so you will not have them anyway |
| `assets/fonts/*.otf`, `*.ttf` | 11 MB | reference copies of the print fonts. Nothing in `css/`, `js/` or `index.html` refers to them — only `assets/fonts/ub/*.woff2` is actually used |

That takes the payload from 185 MB in the repo to about **30 MB**, or **20 MB** if you also drop
the unused fonts.

```bash
rsync -av --delete \
  --exclude '.git' --exclude 'tools' --exclude 'node_modules' \
  --exclude 'langs/*/source' --exclude 'langs/*/source_faq' \
  --exclude 'assets/templates' \
  --exclude 'server.js' --exclude 'package.json' --exclude '*.md' \
  ./ user@server:/var/www/thelivingarkham/
```

## 2. The one rule the server has to follow

**Serve `/` as `index.html`. That is the whole configuration.**

In particular, do **not** add the catch-all rewrite that single-page apps usually need. Routing
here is by URL *fragment* — a link reads `#es/glosario`, and a fragment is never sent to the
server, so every request is for a file that really exists. A catch-all rule would only hide
genuine 404s (a missing `data/faq_de.json`, say) behind a copy of the home page.

(The app does call `history.replaceState`, but only to keep the *fragment* in step as you scroll.
The path never changes, so this stays true.)

The site uses **relative paths only** and declares no `<base>`, so it runs at a domain root or
in a subfolder (`https://example.org/arkham/`) with no changes.

## 3. MIME types

Most servers get these right; the two worth checking on an older config are the last two.

| Extension | Type | If it is wrong |
|---|---|---|
| `.json` | `application/json` | nothing loads at all |
| `.svg` | `image/svg+xml` | product and set icons vanish (they are CSS masks) |
| `.webp` | `image/webp` | the landing hero banner and the Ultimatums & Boons card art do not render |
| `.woff2` | `font/woff2` | those cards fall back to a system font and the fitted text overflows |

```bash
# after deploying
curl -sI https://example.org/data/languages.json | grep -i content-type
curl -sI https://example.org/assets/ub/cards/<any>.webp | grep -i content-type
```

## 4. Compression

Worth doing: `data/` alone is **3.6 MB** of JSON, and it compresses by roughly ten to one. Enable
gzip (or brotli) for `text/html`, `text/css`, `text/javascript`, `application/json` and
`image/svg+xml`. Do **not** compress `.webp` or `.woff2` — they are already compressed.

## 5. Caching

Filenames carry **no content hash**, so a long `max-age` on `css/app.css`, `js/app.js` or
`data/*.json` means readers keep an old copy after you publish an update. Let the browser
revalidate instead — ETag or `Last-Modified` handles it, and a 304 is cheap:

**nginx**

```nginx
root /var/www/thelivingarkham;
index index.html;

# the app and the content: always revalidate, so an update is seen immediately
location ~* \.(html|css|js|json)$ {
    add_header Cache-Control "no-cache";
}
# fonts never change once published
location /assets/fonts/ {
    add_header Cache-Control "public, max-age=31536000, immutable";
}
# pictures change only when the content is rebuilt: a day is a fair trade
location /assets/ {
    add_header Cache-Control "public, max-age=86400";
}
gzip on;
gzip_types text/css text/javascript application/json image/svg+xml;
```

**Apache** (`.htaccess`)

```apache
<IfModule mod_headers.c>
  <FilesMatch "\.(html|css|js|json)$">
    Header set Cache-Control "no-cache"
  </FilesMatch>
  <FilesMatch "\.(woff2)$">
    Header set Cache-Control "public, max-age=31536000, immutable"
  </FilesMatch>
</IfModule>
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/css text/javascript application/json image/svg+xml
</IfModule>
AddType image/webp .webp
```

## 6. Serving the assets from somewhere else

If you move `assets/` to a CDN or a second domain, one feature breaks unless you act: the card
downloader draws the artwork onto a `<canvas>` and exports it, and the images are tagged
`crossorigin="anonymous"` for that reason. From another origin the canvas is tainted and the
export throws, **unless** that origin sends `Access-Control-Allow-Origin`. Same-origin — the
normal case — needs nothing.

## 7. After deploying, check these five

Each one fails for a different reason, so between them they cover the whole configuration.

1. **The home page loads and the language buttons switch.** → `data/languages.json` is served with the right type.
2. **A deep link opened cold** — paste `https://…/#en/glossary` into a new tab. → the fragment router works and `/` really serves `index.html`.
3. **Search finds something** (press `/`, type a rule). → both corpora loaded.
4. **Resources → Ultimatums: download a card.** → `.webp` and `.woff2` types are right and the canvas is not tainted.
5. **FAQ chapter 1 → The list of taboos**: the index opens and a card links out to ArkhamDB. → `data/taboos_*.json` arrived.

## 8. Publishing an update

The content is rebuilt **locally**, never on the server:

```bash
python tools/ingest.py        # rewrites data/ and assets/
```

Read its output before uploading — it reports the coverage of each language against its PDF and
warns about anything that stopped matching. It also lists any **orphaned traced icons**
(`assets/faqsets/*.svg` no longer referenced by any corpus); delete those before uploading, or
they accumulate. Then commit, and re-upload `data/`, `assets/` and `langs/*/ui.json`.

Because the caching above revalidates HTML, CSS, JS and JSON, readers get the new content on
their next visit with no cache busting to do.

## 9. Anything else

* **HTTPS.** Every outbound link (ArkhamDB, ArtStation, the blog, GitHub) is already `https`, so
  there is no mixed content to fix — just serve the site over TLS too.
* **Case.** The project is developed on Windows and served on Linux, where paths are
  case-sensitive. Every path referenced by `index.html`, the CSS, the JS and the language
  registry has been checked against the files on disk and they match; if you rename an asset by
  hand, re-check it, because it will keep working locally and 404 in production.
* **No analytics, no cookies, no third-party scripts.** The only things stored are the reader's
  own choices, in `localStorage`: language, theme, whether the tour has been seen, and the
  viewer's filters.
