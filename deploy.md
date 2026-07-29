# Deploying The Living Arkham

The site is **plain static files** — HTML, CSS, JS, JSON and images. There is no build step on the
server, no runtime, no database, no API keys and nothing to fetch from anywhere else at run time:
the ArkhamDB data is baked into `data/*.json` when the content is built, and ArkhamDB itself is only
ever an outbound link. A `git clone` is the whole site, complete and self-contained.

The only hard requirement is that it is served over **http(s)**, not opened from disk. The app loads
its content with `fetch('data/…json')`, and browsers block `fetch()` on `file://` — so
double-clicking `index.html` shows a blank page. Any HTTP server fixes it.

Two things people usually want:

- **[Run it locally](#run-it-locally)** — to try the site, or to develop.
- **[Put it on a server](#put-it-on-a-vps)** — a worked example on a VPS with your own domain.

The rest is reference: [what to upload](#what-to-upload), [MIME types](#mime-types),
[caching](#caching-and-compression), [serving assets from another origin](#serving-assets-from-another-origin),
[the post-deploy checklist](#after-deploying-check-these-five), and [rebuilding the content](#rebuilding-the-content).

---

## Run it locally

You need **git** and **one** way to serve a folder over HTTP. The repo ships its own zero-dependency
server, so if you have Node you need nothing else.

```bash
git clone https://github.com/fernandoesra/thelivingarkham.git
cd thelivingarkham
node server.js            # → http://localhost:8080   (npm run dev does the same)
```

No Node? Any static server works — the site does not care which:

```bash
python -m http.server 8080      # Python 3, built in  → http://localhost:8080
npx serve .                     # if you have Node but prefer this
php -S localhost:8080           # PHP's built-in server
```

Then open **http://localhost:8080/**. That is the entire "install" — the clone already contains the
data and every asset it needs. You do **not** need Python or the source PDFs just to run the site;
those are only for [rebuilding the content](#rebuilding-the-content), which is separate and optional.

> If you open `index.html` straight from the file manager and the page is blank, that is the
> `file://` limitation above — start one of the servers and use the `http://localhost` URL instead.

---

## Put it on a VPS

A concrete, end-to-end path: an **OVHcloud** VPS running **Ubuntu/Debian** with **nginx**, and a
domain whose DNS is managed at **hostealo**. Any static host works and the ideas carry over — this
is just the version with the real commands filled in.

### 1. Point the domain at the VPS

Find the VPS public address first. It is in the OVHcloud panel, or on the box itself:

```bash
curl -4 ifconfig.me     # IPv4
ip -6 addr              # IPv6, if OVH assigned one
```

In hostealo's **DNS zone** for your domain, set:

| Type | Name | Value |
|---|---|---|
| `A` | `@` | your VPS IPv4 |
| `A` | `www` | your VPS IPv4 |
| `AAAA` | `@` and `www` | your VPS IPv6 *(only if you have one)* |

Leave every other record alone — in particular **do not touch `MX` / mail records**: moving the `A`
record moves only the website, and deleting the mail records would break your email. If the domain
was previously served by hostealo's own hosting, repointing `A` is what hands the site to the VPS.

DNS propagation takes minutes to a few hours. Confirm before moving on:

```bash
dig +short yourdomain.org      # should print the VPS IPv4
```

### 2. First login and hardening

```bash
ssh root@<VPS IP>              # or the user OVH created for you
apt update && apt upgrade -y
```

Recommended, not required: create a non-root sudo user, and open only the ports you need.

```bash
apt install -y ufw
ufw allow OpenSSH
ufw allow 'Nginx Full'         # 80 + 443
ufw enable
```

### 3. Install nginx and put the site on disk

```bash
apt install -y nginx git
git clone https://github.com/fernandoesra/thelivingarkham.git /var/www/thelivingarkham
```

The clone **is** the deployable site — there is no build step. (If you would rather not have `git`
and the build tools sitting in the web root, clone on your own machine and `rsync` up only the
payload instead — see [what to upload](#what-to-upload).)

### 4. The nginx server block

Create `/etc/nginx/sites-available/thelivingarkham`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name yourdomain.org www.yourdomain.org;

    root /var/www/thelivingarkham;
    index index.html;

    # Routing is by URL #fragment (e.g. #es/glosario), which the browser never
    # sends to the server, so every request is for a file that really exists.
    # Serve files as-is and let genuine 404s be 404s. Do NOT add a single-page-app
    # catch-all rewrite here — it would only hide a missing data/faq_de.json behind
    # a copy of the home page.
    location / {
        try_files $uri $uri/ =404;
    }

    # A git checkout in the web root also contains .git/ — never serve dotfiles.
    location ~ /\.(?!well-known) { deny all; }

    # Filenames carry no content hash, so revalidate the app and the content on
    # every visit: an update is then seen immediately, and a 304 is cheap.
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

Enable it and reload:

```bash
ln -s /etc/nginx/sites-available/thelivingarkham /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default      # drop nginx's welcome page
nginx -t && systemctl reload nginx
```

Visit **http://yourdomain.org** — the site should load.

### 5. HTTPS with Let's Encrypt

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d yourdomain.org -d www.yourdomain.org
```

certbot edits the server block for you to listen on 443 with the certificate, and installs a
renewal timer. When it asks, choose to **redirect HTTP to HTTPS**. Then reload once more if needed
and re-check **https://yourdomain.org**.

Every outbound link in the site (ArkhamDB, ArtStation, the blog, GitHub, PayPal) is already
`https`, so there is no mixed content to chase — serving the site itself over TLS is all that is
left.

### 6. Publishing updates later

The content is rebuilt **locally**, never on the server (see [rebuilding](#rebuilding-the-content)).
Once the new `data/`, `assets/` and `langs/*/ui.json` are committed and pushed, the server just
pulls:

```bash
cd /var/www/thelivingarkham && git pull
```

Static files are re-read on the next request, so there is nothing to restart. Because the caching
above revalidates HTML/CSS/JS/JSON, readers get the new content on their next visit with no
cache-busting to do.

---

## What to upload

If you clone directly on the server (the steps above), everything is already in place and you can
skip this. It matters only if you copy files up by hand — e.g. with `rsync`.

**Serve these:**

| Path | Why |
|---|---|
| `index.html` | the page |
| `css/` `js/` | the app |
| `data/*.json` | the built rules — `grimoire_*`, `faq_*`, `taboos_*`, `taboo_cards_*`, `ub.json`, `languages.json` |
| `assets/` | icons, figures, card art, fonts |
| `langs/<code>/ui.json`, `langs/<code>/flag.svg` | each language's interface strings and flag |
| `.nojekyll` | only if you also host on GitHub Pages; harmless otherwise |

**These are for *building* the content, not for serving it — leave them out:**

| Path | What it is |
|---|---|
| `tools/` | the Python build pipeline |
| `server.js`, `package.json` | the local dev server |
| `README.md`, `deploy.md` | docs |
| `langs/*/source/`, `langs/*/source_faq/` | the source PDFs the pipeline reads — **git-ignored**, so a clone will not have them anyway (each folder keeps a README naming the file that belongs there) |
| `assets/templates/` | the ~1 GB Ultimatums & Boons design sources — **git-ignored**; the site ships the optimised WebP under `assets/ub/` instead |
| `langs/_template/` | a scaffold for adding a new language; never referenced by the running site |

The clone payload is about **130 MB**, almost all of it card art (`assets/taboo` ≈ 74 MB,
`assets/ub` ≈ 27 MB). The rest of the site is small.

> **Do not delete the font masters in `assets/fonts/`.** The `*.woff2` files are served; the
> `*.otf` / `*.ttf` are the print masters and are *not* served, but they are build inputs
> (`tools/ub_fonts.py` cuts the `assets/fonts/ub/*.woff2` from them, and `css/app.css` names
> `Teutonic.ttf` as `--ff-head`). You may skip uploading the masters, but keep them in the repo.

```bash
rsync -av --delete \
  --exclude '.git' --exclude 'tools' --exclude 'node_modules' \
  --exclude 'langs/*/source' --exclude 'langs/*/source_faq' --exclude 'langs/_template' \
  --exclude 'assets/templates' \
  --exclude 'server.js' --exclude 'package.json' --exclude '*.md' \
  ./ user@server:/var/www/thelivingarkham/
```

The site uses **relative paths only** and declares no `<base>`, so it runs at a domain root or in a
subfolder (`https://example.org/arkham/`) with no changes.

---

## MIME types

Most servers get these right; the two worth checking on an older config are the last two. nginx and
the repo's `server.js` already handle all four.

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

On **Apache**, the equivalents live in `.htaccess`:

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

---

## Caching and compression

Covered by the server block above, and worth understanding:

- **Revalidate the app and the content.** Filenames carry no content hash, so a long `max-age` on
  `css/app.css`, `js/app.js` or `data/*.json` would leave readers on an old copy after you publish.
  `no-cache` (revalidate, 304 when unchanged) keeps updates instant and cheap.
- **Cache the assets.** Fonts are immutable for a year; images for a day.
- **Compress text, not media.** `data/` compresses roughly ten to one; gzip (or brotli) `text/html`,
  `text/css`, `text/javascript`, `application/json`, `image/svg+xml`. Do **not** compress `.webp` or
  `.woff2` — they are already compressed and you would only spend CPU.

---

## Serving assets from another origin

If you move `assets/` to a CDN or a second domain, one feature breaks unless you act: the card
downloader draws the artwork onto a `<canvas>` and exports it, and the images are tagged
`crossorigin="anonymous"` for that reason. From another origin the canvas is *tainted* and the
export throws — **unless** that origin sends `Access-Control-Allow-Origin`. Same-origin (the normal
case, and everything above) needs nothing.

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
requires Python 3.9+ and the source PDFs, which are **git-ignored** (see the table above), so this
step is not part of a normal deploy.

```bash
pip install -r tools/requirements.txt     # PyMuPDF, once
python tools/ingest.py                     # rewrites data/ and assets/
```

Read its output before uploading: it reports each language's coverage against its PDF and warns
about anything that stopped matching. It also lists any **orphaned traced icons**
(`assets/faqsets/*.svg` no longer referenced by any corpus) — delete those before uploading, or they
accumulate. Then commit, push, and on the server `git pull`.

> Rebuilds show a half-built site mid-run — the icon tables and cross-language data look broken
> until `ingest.py` finishes. Let it complete before judging the result.

---

## Notes

- **Case sensitivity.** The project is developed on Windows and served on Linux, where paths are
  case-sensitive. Every path referenced by `index.html`, the CSS, the JS and the language registry
  has been checked against the files on disk and they match; if you rename an asset by hand, re-check
  it, because it will keep working locally and 404 in production.
- **No analytics, no cookies, no third-party scripts.** The only things stored are the reader's own
  choices, in `localStorage`: language, theme, whether the tour has been seen, and the viewer's
  filters.
