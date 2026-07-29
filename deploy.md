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

## Put it on a VPS

Before the commands, the thing that decides the whole shape of this: **there is nothing to compile
and nothing of ours to keep alive.** `js/app.js` and `css/app.css` are written by hand and served
exactly as they are — no bundler, no `npm install`, no `node_modules`, no build output. And
`server.js` in this repo is a *development* server: it sends `Cache-Control: no-store` on purpose so
a rebuild is visible immediately, which is the opposite of what you want in public. It has no
business on the VPS.

So on the server the only thing that runs is **nginx**, reading files off the disk. "Restart it if
it falls over" is therefore a question about nginx and about the box rebooting — never about the
app — and [step 6](#6-make-it-survive-a-crash-and-a-reboot) is where it is answered.

The worked example is an **OVHcloud** VPS running **Ubuntu/Debian**, with the domain's DNS managed
at **hostealo**. Any provider works and every step carries over; this is just the version with the
real commands filled in. Run them as root, or put `sudo` in front.

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

DNS takes minutes to a few hours, and the certificate in step 5 will not be issued until it has
propagated. Confirm before moving on:

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

That is the deploy. The clone **is** the site — about 131 MB, complete, nothing to install after it.
nginx only ever reads these files, so root-owned and world-readable (the default) is all they need.

If you would rather not have `.git` and the Python build tools sitting in the web root, clone on your
own machine and `rsync` up only the payload instead — see [what to upload](#what-to-upload).

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
    location / { try_files $uri $uri/ =404; }

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

certbot edits the server block for you to listen on 443 with the certificate, and installs a renewal
timer. When it asks, choose to **redirect HTTP to HTTPS**. Then re-check **https://yourdomain.org**.

Every outbound link in the site (ArkhamDB, ArtStation, the blog, GitHub, PayPal) is already `https`,
so there is no mixed content to chase — serving the site itself over TLS is all that is left.

### 6. Make it survive a crash and a reboot

Two different failures, and the second is the one that actually happens. nginx is a C daemon that
serves static files; it does not leak, wedge or die on its own. What does happen is that the **VPS
reboots** — a kernel update, OVH migrating the host, a power event — so the first line here matters
far more than the rest.

```bash
systemctl enable nginx        # start at boot, from now on
systemctl is-enabled nginx    # → enabled
```

`apt install nginx` normally enables it already. Run it anyway; it is idempotent, and this is the
one thing that must not be assumed.

For the crash case, tell systemd to bring nginx back if it ever does die. Debian's unit ships with
**no `Restart=` line at all**, so by default a killed master stays dead until someone notices:

```bash
systemctl edit nginx
```

That opens an empty override file (`/etc/systemd/system/nginx.service.d/override.conf`). Put this
between the comment markers, save, and apply it:

```ini
[Service]
Restart=on-failure
RestartSec=2s
```

```bash
systemctl daemon-reload && systemctl restart nginx
```

Now verify both, rather than trusting the file:

```bash
# The crash: kill the master outright. systemd should have it back within ~2 s.
kill -9 $(cat /run/nginx.pid); sleep 3; systemctl is-active nginx    # → active

# The reboot: the honest test. The SSH session dies with it.
reboot
```

Give it a minute, then from **your own machine** — not the VPS:

```bash
curl -sI https://yourdomain.org | head -1        # → HTTP/2 200
```

The certificate renews itself — certbot installed a systemd timer when it issued it. Check that it
is armed, and rehearse a renewal without touching the live certificate:

```bash
systemctl list-timers | grep certbot     # should show a next run
certbot renew --dry-run
```

And if you want the machine to patch itself:

```bash
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

One failure does **not** self-heal, and it is the only one you can cause: a server block that does
not parse. nginx will refuse to start on the next boot and the site stays down until you fix it by
hand. `nginx -t` before every reload is the entire discipline — `systemctl reload` on a bad config
keeps the old one running and is harmless; a reboot on a bad config is not.

### 7. Publishing updates later

The content is rebuilt **locally**, never on the server (see [rebuilding](#rebuilding-the-content)).
Once the new files are committed and pushed, the server just pulls:

```bash
cd /var/www/thelivingarkham && git pull
```

Static files are re-read on the next request, so there is **nothing to restart** — no reload, no
service, no cache to clear. The caching policy above revalidates HTML/CSS/JS/JSON, so readers see
the new content on their next visit with no cache-busting to do.

### Any other kind of host

The same site, fewer steps. Shared hosting with a control panel: upload the payload into
`public_html` / `www` / `htdocs` and you are done — you cannot edit nginx, so use the
[`.htaccess` block](#other-servers-and-mime-types) instead, and lean on the
[five checks](#after-deploying-check-these-five). Static-site platforms (GitHub Pages, Netlify,
Cloudflare Pages): point them at the repo with **no build command** and the root as the publish
directory. Nothing in steps 4–6 applies, because there is no server of yours to configure or keep
alive.

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

## Other servers and MIME types

The [nginx block in step 4](#4-the-nginx-server-block) is the reference configuration; this is the
same four ideas — no SPA rewrite, no dotfiles, revalidate the app, compress the JSON — for a server
you do not fully control. All of it is optional: the site works on the defaults.

**Apache**, in `.htaccess` (which shared hosting normally does allow):

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
