# Deploying The Living Arkham

The site is **plain static files** — HTML, CSS, JS, JSON and images. There is no build step, no
runtime, no database, no API keys and nothing fetched from anywhere at run time: the rules data is
baked into `data/*.json` when the content is built, and ArkhamDB is only ever an outbound link.
**A clone of the repository *is* the finished site.**

There is one hard requirement: it must be served over **http(s)**, not opened from disk. The app
loads its content with `fetch('data/…json')`, and browsers block that on `file://` — so
double-clicking `index.html` shows a blank page. Any HTTP server fixes it.

- **[Run it locally](#run-it-locally)** — to read the site, or to develop.
- **[Put it on a VPS](#put-it-on-a-vps)** — the full path, with the real commands.

The rest is reference: [what to upload](#what-to-upload),
[other servers and MIME types](#other-servers-and-mime-types), [the checks after deploying](#after-deploying-check-these-five),
[rebuilding the content](#rebuilding-the-content) and a few [notes](#notes).

---

## Run it locally

You need **git** and any one way to serve a folder over HTTP. The repo ships its own
zero-dependency server, so if you have Node you need nothing else:

```bash
git clone https://github.com/fernandoesra/thelivingarkham.git
cd thelivingarkham
node server.js            # → http://localhost:8080   (npm run dev does the same)
node server.js 8137       # …or any other port
```

No Node? Any static server works — the site does not care which:

```bash
python -m http.server 8080      # Python 3, built in
npx serve .
php -S localhost:8080
```

Then open **http://localhost:8080/**. That is the entire "install": the clone already contains the
data and every asset it needs. You do **not** need Python or the source PDFs just to run the site —
those are only for [rebuilding the content](#rebuilding-the-content), which is optional and separate.

> If you open `index.html` straight from the file manager and the page is blank, that is the
> `file://` limitation above. Start one of the servers and use the `http://localhost` URL instead.

---

## Put it on a server

The same four steps whatever the machine: a rented server you administer, a shared hosting account
with a control panel, a static-site platform, or a box on your own network. If it can serve a folder
of files over HTTP, it can serve this site.

### 1. Get the files onto the server

Everything goes into the server's **web directory** — the folder it publishes. Where that is depends
on the machine: `/var/www/<something>` is the usual place on Linux, and hosting with a control panel
normally calls it `public_html`, `www` or `htdocs`. Find yours, and use it wherever this page writes
`/var/www/thelivingarkham`, which is only an example.

Either clone straight into it — the path after the URL is where the clone lands…

```bash
git clone https://github.com/fernandoesra/thelivingarkham.git /var/www/thelivingarkham
```

…or copy the folder up from your own machine with whatever you have — the panel's file manager,
FTP/SFTP, or `rsync` (see [what to upload](#what-to-upload)).

There is nothing to compile, install or keep running. The files are the site.

### 2. Point the web server at that folder

Set the document root to the folder and let `index.html` be the index file. Two things to get right,
both of them defaults on most servers:

- **Serve the files exactly as they are — do not add a single-page-app catch-all rewrite.** Routing
  happens in the URL `#fragment` (`#es/glosario`), which the browser never sends to the server, so
  every request is for a file that really exists. A catch-all would only hide a missing
  `data/faq_de.json` behind a copy of the home page. Let genuine 404s be 404s.
- **Do not serve dotfiles.** If you cloned into the web directory, `.git/` is sitting in it.

If you can edit the server configuration, the [ready-made blocks below](#server-configuration) do
both, plus caching and compression. If you cannot — most shared hosting — the defaults are usually
fine; just run the [five checks](#after-deploying-check-these-five) at the end.

### 3. Turn on HTTPS

Use whichever certificate your server or hosting panel offers; the site does not care where it comes
from. Enable the HTTP → HTTPS redirect while you are there. Every outbound link in the site is
already `https`, so there is no mixed content to chase — serving the site itself over TLS is all
that is left.

If the domain is new, point its DNS at the server *before* asking for a certificate: an `A` record
to the server's IPv4 address (and `AAAA` if it has IPv6), for both the bare domain and `www`. Leave
every other record alone — in particular the `MX` / mail records, which have nothing to do with the
website and would take your email down with them. DNS takes minutes to a few hours; `dig +short
yourdomain.org` should print the server's address before you go on.

### 4. Publishing updates later

The content is rebuilt **locally**, never on the server (see
[rebuilding](#rebuilding-the-content)). Once the new files are committed and pushed, the server just
pulls:

```bash
cd /var/www/thelivingarkham && git pull
```

Or re-upload the folders that changed. Static files are re-read on the next request, so there is
nothing to restart, and the caching policy below means readers see the new content on their next
visit with no cache-busting to do.

---

## What to upload

If you cloned on the server, everything is already in place — skip this. It matters only when you
copy files up by hand.

**Serve these:**

| Path | Why |
|---|---|
| `index.html` | the page |
| `css/` `js/` | the app |
| `data/*.json` | the built rules — `grimoire_*`, `faq_*`, `taboos_*`, `taboo_cards_*`, `ub.json`, `languages.json` |
| `assets/` | icons, figures, card art, fonts |
| `langs/<code>/ui.json`, `langs/<code>/flag.svg` | each language's interface strings and flag |
| `.nojekyll` | only for static hosts that would otherwise ignore files beginning with `_`; harmless everywhere else |

**These build the content, they do not serve it — leave them out:**

| Path | What it is |
|---|---|
| `tools/` | the Python build pipeline |
| `server.js`, `package.json` | the local dev server |
| `README.md`, `deploy.md` | docs |
| `langs/*/source/`, `langs/*/source_faq/` | the source PDFs the pipeline reads — **git-ignored**, so a clone will not have them anyway (each folder keeps a README naming the file that belongs there) |
| `assets/templates/` | the ~1 GB Ultimatums & Boons design sources — **git-ignored**; the site ships the optimised WebP under `assets/ub/` instead |
| `langs/_template/` | a scaffold for adding a new language; never referenced by the running site |

```bash
rsync -av --delete \
  --exclude '.git' --exclude 'tools' --exclude 'node_modules' \
  --exclude 'langs/*/source' --exclude 'langs/*/source_faq' --exclude 'langs/_template' \
  --exclude 'assets/templates' \
  --exclude 'server.js' --exclude 'package.json' --exclude '*.md' \
  ./ user@server:/var/www/thelivingarkham/
```

The payload is about **131 MB**, almost all of it card art (`assets/taboo` ≈ 74 MB, `assets/ub`
≈ 27 MB). The rest of the site is small.

The site uses **relative paths only** and declares no `<base>`, so it runs at a domain root or in a
subfolder (`https://example.org/arkham/`) with no changes.

> **Do not delete the font masters in `assets/fonts/`.** The `*.woff2` files are served; the
> `*.otf` / `*.ttf` are print masters and are *not* served, but they are build inputs
> (`tools/ub_fonts.py` cuts `assets/fonts/ub/*.woff2` from them, and `css/app.css` names
> `Teutonic.ttf`). You may skip uploading the masters, but keep them in the repo.

---

## Server configuration

Optional — the site works without any of it — but this is what a well-configured server does. Four
things, and the comments say why.

**nginx**, as `/etc/nginx/sites-available/thelivingarkham`, enabled with a symlink into
`sites-enabled/` and `nginx -t && systemctl reload nginx`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name yourdomain.org www.yourdomain.org;

    root /var/www/thelivingarkham;
    index index.html;

    # Routing is by #fragment, which never reaches the server, so serve files
    # as-is and let genuine 404s be 404s. No SPA catch-all rewrite here.
    location / { try_files $uri $uri/ =404; }

    # A git checkout in the web root also contains .git/ — never serve dotfiles.
    location ~ /\.(?!well-known) { deny all; }

    # Filenames carry no content hash, so revalidate the app and the content on
    # every visit: an update is seen immediately, and a 304 is cheap.
    location ~* \.(html|css|js|json)$ { add_header Cache-Control "no-cache"; }
    # Fonts never change once published.
    location /assets/fonts/ { add_header Cache-Control "public, max-age=31536000, immutable"; }
    # Pictures change only when the content is rebuilt: a day is a fair trade.
    location /assets/ { add_header Cache-Control "public, max-age=86400"; }

    # data/ alone is several MB of JSON and compresses ~10:1. Do NOT gzip .webp
    # or .woff2 — they are already compressed.
    gzip on;
    gzip_types text/css text/javascript application/json image/svg+xml;
}
```

**Apache**, the same ideas in `.htaccess`:

```apache
<IfModule mod_headers.c>
  <FilesMatch "\.(html|css|js|json)$"><Header set Cache-Control "no-cache"></FilesMatch>
  <FilesMatch "\.woff2$"><Header set Cache-Control "public, max-age=31536000, immutable"></FilesMatch>
</IfModule>
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/css text/javascript application/json image/svg+xml
</IfModule>
AddType image/webp .webp
```

### MIME types

Most servers get these right; the last two are the ones worth checking on an older configuration.
nginx and the repo's `server.js` already handle all four.

| Extension | Type | If it is wrong |
|---|---|---|
| `.json` | `application/json` | nothing loads at all |
| `.svg` | `image/svg+xml` | product and set icons vanish (they are CSS masks) |
| `.webp` | `image/webp` | the hero banner, the Ultimatums & Boons art and the taboo card plates do not render |
| `.woff2` | `font/woff2` | those cards fall back to a system font and the fitted text overflows |

```bash
curl -sI https://yourdomain.org/data/languages.json | grep -i content-type
curl -sI https://yourdomain.org/assets/ub/cards/boon-of-athena.webp | grep -i content-type
```

---

## After deploying, check these five

Each one fails for a different reason, so between them they cover the whole configuration.

1. **The home page loads and the language buttons switch.** → `data/languages.json` is served with the right type.
2. **A deep link opened cold** — paste `https://yourdomain.org/#en/glossary` into a new tab. → the fragment router works and `/` really serves `index.html`.
3. **Search finds something** (press `/`, type a rule). → both corpora loaded.
4. **Resources → Ultimatums & Boons: download a card.** → `.webp` and `.woff2` types are right and the canvas is not tainted.
5. **FAQ chapter 1 → The list of taboos**: the index opens, a card renders, and it links out to ArkhamDB. → `data/taboos_*.json` and `data/taboo_cards_*.json` arrived.

---

## Rebuilding the content

Only needed to change the data, and only ever done **locally** — the server never builds. It
requires Python 3.9+ and the source PDFs, which are **git-ignored**, so this is not part of a normal
deploy.

```bash
pip install -r tools/requirements.txt     # PyMuPDF, once
python tools/ingest.py                     # rewrites data/ and assets/
```

Read its output before uploading: it reports each language's coverage against its PDF and warns
about anything that stopped matching. It also lists **orphaned traced icons**
(`assets/faqsets/*.svg` no longer referenced by any corpus) — delete those, or they accumulate.
Then commit, push, and on the server `git pull`.

> A rebuild takes about ten minutes and shows a half-built site while it runs — the icon tables and
> the cross-language data look broken until `ingest.py` finishes. Let it complete before judging it.

---

## Notes

- **Case sensitivity.** The project is developed on Windows and usually served on Linux, where paths
  are case-sensitive. Every path referenced by `index.html`, the CSS, the JS and the language
  registry matches the files on disk; if you rename an asset by hand, re-check it, because it will
  keep working locally and 404 in production.
- **Assets on another origin.** If you move `assets/` to a different domain, the card downloader
  breaks unless that origin sends `Access-Control-Allow-Origin`: it draws the artwork onto a
  `<canvas>` and exports it, which a cross-origin image taints. Same-origin — the normal case —
  needs nothing.
- **No analytics, no cookies, no third-party scripts.** The only things stored are the reader's own
  choices, in `localStorage`: language, theme, whether the tour has been seen, and the viewer's
  filters.
