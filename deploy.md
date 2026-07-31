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
[traffic statistics](#traffic-statistics), [rebuilding the content](#rebuilding-the-content) and a
few [notes](#notes).

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

So on the server the only thing that runs is a **web server**, reading files off the disk. "Restart
it if it falls over" is therefore a question about that one daemon and about the box rebooting —
never about the app — and [step 5](#5-make-it-survive-a-crash-and-a-reboot) is where it is answered.

The web server here is **[Caddy](https://caddyserver.com/)**, because for a site with no build and
no backend it removes most of the remaining work: it obtains and renews the TLS certificate by
itself with nothing to configure, redirects HTTP to HTTPS by default, and refuses to apply a config
that does not parse instead of falling over on the next boot. The
[nginx equivalent](#nginx-instead-of-caddy) is at the end if you would rather.

The worked example is the machine the site actually runs on: an **OVHcloud** VPS on
**Ubuntu 26.04**, with the domain registered and its DNS zone hosted at OVH too. Any provider works
and every step carries over; this is just the version with the real commands filled in. Run them as
root, or put `sudo` in front — OVH gives you an `ubuntu` user, not root.

### 1. Point the domain at the VPS

Find the VPS public address first. It is in the OVHcloud panel, or on the box itself:

```bash
curl -4 ifconfig.me     # IPv4
ip -6 addr              # IPv6, if OVH assigned one
```

The zone is under **Web Cloud → Domains → your domain → DNS zone**. Four records:

| Type | Subdomain | Target |
|---|---|---|
| `A` | *(empty)* | your VPS IPv4 |
| `A` | `www` | your VPS IPv4 |
| `AAAA` | *(empty)* | your VPS IPv6 *(only if you have one)* |
| `AAAA` | `www` | your VPS IPv6 |

**Never touch the `MX` records** — the `mx*.mail.ovh.net` entries are the domain's mail, they have
nothing to do with the website, and deleting them takes your email down with them. Leave the `SPF`
and OVH's `ownercheck` `TXT` alone too.

Two things will waste an hour each if you do not know them:

- **A web redirection owns the records it creates.** A domain freshly registered at OVH normally
  ships with one — the parking page. In the zone it looks like `A` records pointing at
  `213.186.33.5` (which reverse-resolves to `redirect.ovh.net`) plus `TXT` markers such as
  `"1|www.yourdomain.com"`. Those belong to the redirection service, not to you, so editing them can
  simply be undone. Delete the redirection first, in the **Redirection** tab; it takes its own `A`
  and `TXT` records with it, and then the zone is yours to fill in.
- **The panel shows a stale snapshot for several minutes.** While the blue *"actions have been
  carried out recently on the DNS zone"* banner is up, the record list is frozen — it will happily
  keep listing an `A` record that has already been deleted. Ask the authoritative server instead,
  which is never wrong:

  ```bash
  dig +short yourdomain.com @dns106.ovh.net       # use your zone's own NS
  nslookup -type=A yourdomain.com dns106.ovh.net  # same thing without dig
  ```

Do all of this **first**. Caddy asks Let's Encrypt for the certificate the moment it starts, and
that fails, loudly and repeatedly, until the name resolves to this machine. OVH warns about 24
hours; in practice it is minutes. Confirm against a public resolver — that is what the world sees,
and what Let's Encrypt will query:

```bash
dig +short yourdomain.com @1.1.1.1        # should print the VPS IPv4
dig +short yourdomain.com AAAA @8.8.8.8   # and the IPv6
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
ufw allow 80/tcp               # needed even after HTTPS: the redirect, and ACME's HTTP challenge
ufw allow 443/tcp
ufw allow 443/udp              # Caddy serves HTTP/3 by default, which is QUIC over UDP
ufw enable
```

Caddy ships no ufw application profile, so the ports go in by number. Miss `443/udp` and nothing
breaks visibly — browsers just quietly fall back to HTTP/2.

### 3. Install Caddy and put the site on disk

Caddy is not in Debian's or Ubuntu's own repositories in a version worth using, so add the project's
apt repository first — this is the official set of commands from
[caddyserver.com/docs/install](https://caddyserver.com/docs/install):

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl git
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy
```

The package starts Caddy immediately on its default config — a placeholder page on port 80. That is
expected; the next step replaces it.

Then the site itself:

```bash
git clone https://github.com/fernandoesra/thelivingarkham.git /var/www/thelivingarkham
```

That is the deploy. The clone **is** the site — about 131 MB, complete, nothing to install after it.
Caddy runs as the unprivileged `caddy` user and only ever reads these files, so root-owned and
world-readable (what `git clone` gives you) is all they need.

If you would rather not have `.git` and the Python build tools sitting in the web root, clone on your
own machine and `rsync` up only the payload instead — see [what to upload](#what-to-upload).

### 4. The Caddyfile

Replace `/etc/caddy/Caddyfile` with this. Put your real domain on the first line and your real
address in `email` — that is the whole configuration, TLS included:

```caddy
{
	# Let's Encrypt sends expiry and problem notices here. Not required, worth having.
	email you@yourdomain.org
}

yourdomain.org, www.yourdomain.org {
	root * /var/www/thelivingarkham
	file_server

	# data/ alone is several MB of JSON and compresses ~10:1. Caddy already skips
	# content that is compressed on the wire, so .webp and .woff2 are left alone.
	encode zstd gzip

	# A git checkout in the web root also contains .git/ — never serve dotfiles.
	# .well-known stays reachable for anything else that wants it; Caddy answers
	# its own ACME challenges before this block is ever consulted.
	@dotfiles {
		path_regexp ^/(.*/)?\.
		not path /.well-known/*
	}
	respond @dotfiles 404

	# Filenames carry no content hash, so revalidate the app and the content on
	# every visit: an update is then seen immediately, and a 304 is cheap.
	@app path *.html *.css *.js *.json
	header @app Cache-Control "no-cache"

	# Pictures change only when the content is rebuilt: a day is a fair trade.
	# Fonts never change once published, so they are excluded here and pinned below.
	@pics {
		path /assets/*
		not path /assets/fonts/*
	}
	header @pics Cache-Control "public, max-age=86400"

	@fonts path /assets/fonts/*
	header @fonts Cache-Control "public, max-age=31536000, immutable"
}
```

There is deliberately **no `try_files {path} /index.html` fallback**. Routing happens in the URL
`#fragment` (`#es/glosario`), which the browser never sends to the server, so every request is for a
file that really exists. An SPA fallback would only hide a missing `data/faq_de.json` behind a copy
of the home page. Let genuine 404s be 404s.

Check it and load it:

```bash
caddy fmt --overwrite /etc/caddy/Caddyfile      # tabs, canonical spacing
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Then open **https://yourdomain.org** — note the `https`. You never asked for a certificate: Caddy
saw a public domain name in the config, obtained one from Let's Encrypt on startup, and began
redirecting `http` to it.

**Give it a good fifteen seconds before you judge it.** Two names means two ACME orders, run one
after the other, and a `curl` fired too early comes back empty even though nothing is wrong —
which reads exactly like a failure. The log is what tells you the truth:

```bash
journalctl -u caddy -n 40 --no-pager | grep -E "certificate obtained|authz_status|error"
```

One `certificate obtained successfully` per name and you are done. If instead you see ACME errors,
they are almost always DNS not yet pointing here (step 1) — and the `served key authentication`
lines are worth reading either way, because they are Let's Encrypt reaching your port 80 from
several places at once, over IPv6 as well if you added the `AAAA` records.

Every outbound link in the site (ArkhamDB, ArtStation, the blog, GitHub, PayPal) is already `https`,
so there is no mixed content to chase.

### 5. Make it survive a crash and a reboot

Two different failures, and the second is the one that actually happens. Caddy serving static files
does not leak, wedge or die on its own. What does happen is that the **VPS reboots** — a kernel
update, OVH migrating the host, a power event — so the first line here matters far more than the
rest.

```bash
systemctl enable caddy        # start at boot, from now on
systemctl is-enabled caddy    # → enabled
```

The `.deb` normally enables it already. Run it anyway; it is idempotent, and this is the one thing
that must not be assumed.

The crash case needs work, because **Caddy's packaged unit ships no `Restart=` line at all** —
verified on 2.11.4 from the cloudsmith repo, where `systemctl cat caddy | grep -i restart` prints
nothing. Without the override below, a Caddy that dies stays dead until somebody notices. This is
not optional.

Write the drop-in directly rather than through `systemctl edit`, which opens an interactive editor
and is no use if you are pasting a block of commands:

```bash
mkdir -p /etc/systemd/system/caddy.service.d
tee /etc/systemd/system/caddy.service.d/override.conf > /dev/null <<'EOF'
[Service]
Restart=on-failure
RestartSec=2s
EOF
systemctl daemon-reload && systemctl restart caddy
systemctl show caddy -p Restart          # → Restart=on-failure
```

The drop-in wins over whatever the package ships, so it is safe to apply unconditionally — worth
knowing if a future release does add a `Restart=` of its own. `on-failure` is the one to want:
`on-abnormal`, which some units use, covers a signal or a watchdog timeout but *not* an ordinary
non-zero exit.

Now verify both, rather than trusting the file:

```bash
# The crash: kill it outright. systemd should have it back within ~2 s.
systemctl kill -s SIGKILL caddy; sleep 3; systemctl is-active caddy    # → active

# The reboot: the honest test. The SSH session dies with it.
reboot
```

Give it a minute, then from **your own machine** — not the VPS:

```bash
curl -sI https://yourdomain.org | head -1        # → HTTP/2 200
```

The certificate renews itself and there is no timer to check: Caddy keeps its own renewals in
process, starting well before expiry, and stores the certificate under `/var/lib/caddy` so a restart
does not re-issue it. This is the part certbot needed a cron job for.

If you want the machine to patch itself too:

```bash
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

One failure does not self-heal, and it is the only one you can cause: a Caddyfile that does not
parse. `systemctl reload caddy` is safe — Caddy validates the new config and keeps serving the old
one if it fails — but a **reboot** on a saved-but-broken Caddyfile leaves the site down until you
fix it by hand. So `caddy validate` after every edit, and never leave a config unreloaded overnight.

### 6. Publishing updates later

The content is rebuilt **locally**, never on the server (see [rebuilding](#rebuilding-the-content)).
Once the new files are committed and pushed, the server just pulls:

```bash
cd /var/www/thelivingarkham && git pull
```

Static files are re-read on the next request, so there is **nothing to restart** — no reload, no
service, no cache to clear. The caching policy above revalidates HTML/CSS/JS/JSON, so readers see
the new content on their next visit with no cache-busting to do.

### More than one domain, and the `www` question

Serve the site on **one** name and redirect every other name to it. Two addresses returning identical
content is duplicate content: search engines split the ranking between them instead of adding it up,
and two "real" URLs end up in links and bookmarks. A `301` says *the real address is this one* and
consolidates everything.

`www` counts. If both `example.org` and `www.example.org` serve the site, that is the same duplicate.
Pick one — bare is the usual choice — and redirect the other.

```caddy
example.org {
	root * /var/www/thelivingarkham
	file_server
	# …the rest of the site block
}

www.example.org, otherdomain.org, www.otherdomain.org {
	redir https://example.org{uri} permanent
}
```

`{uri}` carries the path and query across, so an old deep link reaches the same page instead of
landing on the home page. `permanent` is the `301`.

Two things about ordering, both of which can take the site down if you get them wrong:

- **Point the new name's DNS at the server *before* adding it to the Caddyfile.** Reload with a name
  that does not resolve yet and Caddy retries the ACME order in a loop; Let's Encrypt rate-limits
  failures, so those attempts are not free.
- **Never flip which name is canonical before the new one resolves.** The old name would `301` to a
  domain that answers nothing, and then *both* addresses are dead rather than one. Verify with a
  public resolver first — `dig +short newname.org @1.1.1.1` — and keep a `Caddyfile.bak` so
  reverting is one `cp` and a reload.

Nothing in the repository names a domain — no `<base>`, no `rel="canonical"`, no absolute URLs in the
JS or the data — so switching the canonical name is a server-side change only. There is nothing to
rebuild.

### nginx instead of Caddy

Same site, same four ideas, more moving parts — you write the server block, you install certbot, and
you check its renewal timer yourself. Worth it if you already run nginx on the box.

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name yourdomain.org www.yourdomain.org;

    root /var/www/thelivingarkham;
    index index.html;

    # Routing is by #fragment, which never reaches the server. No SPA catch-all.
    location / { try_files $uri $uri/ =404; }

    # A git checkout in the web root also contains .git/ — never serve dotfiles.
    location ~ /\.(?!well-known) { deny all; }

    # Filenames carry no content hash: revalidate the app and the content.
    location ~* \.(html|css|js|json)$ { add_header Cache-Control "no-cache"; }
    location /assets/fonts/ { add_header Cache-Control "public, max-age=31536000, immutable"; }
    location /assets/ { add_header Cache-Control "public, max-age=86400"; }

    # Do NOT gzip .webp or .woff2 — they are already compressed.
    gzip on;
    gzip_types text/css text/javascript application/json image/svg+xml;
}
```

```bash
ln -s /etc/nginx/sites-available/thelivingarkham /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default          # drop nginx's welcome page
nginx -t && systemctl reload nginx
apt install -y certbot python3-certbot-nginx
certbot --nginx -d yourdomain.org -d www.yourdomain.org   # choose the HTTP→HTTPS redirect
```

[Step 5](#5-make-it-survive-a-crash-and-a-reboot) applies unchanged with `nginx` in place of
`caddy` — and Debian's nginx unit ships with **no `Restart=` at all**, so the override is not
optional there. Add `systemctl list-timers | grep certbot` and `certbot renew --dry-run` to the
checks, since the certificate no longer renews itself from inside the server.

### Any other kind of host

The same site, fewer steps. Shared hosting with a control panel: upload the payload into
`public_html` / `www` / `htdocs` and you are done — you cannot install a web server there, so use
the [`.htaccess` block](#other-servers-and-mime-types) instead, and lean on the
[five checks](#after-deploying-check-these-five). Static-site platforms (GitHub Pages, Netlify,
Cloudflare Pages): point them at the repo with **no build command** and the root as the publish
directory. Nothing in steps 3–5 applies, because there is no server of yours to configure or keep
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
| `data/*.json` | the built rules — `grimoire_*`, `faq_*`, `taboos_*`, `taboo_cards_*`, `ub.json`, `languages.json` — plus the hand-authored `releases.json` (version notes, fetched when the footer's release panel opens) |
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
> (`tools/ub_fonts.py` cuts the served `assets/fonts/ub/ub-title.woff2` — the blackletter
> card-title face — from `Teutonic.ttf`). You may skip uploading the masters, but keep them
> in the repo.

---

## Other servers and MIME types

The [Caddyfile in step 4](#4-the-caddyfile) is the reference configuration; this is the same four
ideas — no SPA rewrite, no dotfiles, revalidate the app, compress the JSON — for a server you do not
fully control. All of it is optional: the site works on the defaults.

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
Caddy, nginx and the repo's `server.js` already handle all four.

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

Those five need a browser. Everything the *server* is responsible for can be checked in one paste —
run this before you open the site, because it tells you which of the five would fail and why:

```bash
D=https://yourdomain.org
printf "%-30s " "root"                    ; curl -so /dev/null -w "%{http_code} HTTP/%{http_version}\n" $D/
printf "%-30s " "www"                     ; curl -so /dev/null -w "%{http_code}\n" https://www.yourdomain.org/
printf "%-30s " "http -> https"           ; curl -so /dev/null -w "%{http_code} -> %{redirect_url}\n" http://yourdomain.org/
printf "%-30s " "data/languages.json"     ; curl -so /dev/null -w "%{http_code} %{content_type}\n" $D/data/languages.json
printf "%-30s " "teutonic.woff2"          ; curl -so /dev/null -w "%{http_code} %{content_type}\n" $D/assets/fonts/teutonic.woff2
printf "%-30s " "a card .webp"            ; curl -so /dev/null -w "%{http_code} %{content_type}\n" $D/assets/ub/backs/boon.webp
printf "%-30s " ".git/config (want 404)"  ; curl -so /dev/null -w "%{http_code}\n" $D/.git/config
curl -sI -H "Accept-Encoding: gzip,zstd" $D/data/languages.json | grep -i content-encoding
curl -sI $D/js/app.js                     | grep -i cache-control   # → no-cache
curl -sI $D/assets/fonts/teutonic.woff2   | grep -i cache-control   # → immutable
curl -sI $D/assets/ub/backs/boon.webp     | grep -i cache-control   # → max-age=86400
```

Wanted: `200` and `HTTP/2` at the root, `application/json`, `font/woff2` and `image/webp` on their
three files, `308` on the redirect, `gzip` or `zstd` on the JSON — and **`404` on `.git/config`**.
That last one is the only line that is about safety rather than function: if you cloned into the web
root, the entire repository history is sitting on disk under the document root, and the `@dotfiles`
matcher is the one thing standing between it and the internet. A `200` there means anyone can
download it.

---

## Traffic statistics

Google Analytics is the wrong tool here, and not on principle: it is a third-party script that sets
cookies, it needs a consent banner in the EU, it sends your readers' data to Google — and between a
third and a half of visitors block it, so you pay all of that for a number that is wrong anyway.

The site already generates everything you need. Caddy can log every request it serves, and
**GoAccess** turns those logs into a dashboard. No JavaScript on the page, no cookies, no consent
banner, no third party: the reader is not involved at all. What you give up is in-page events — the
logs know a `.webp` was requested, not that someone clicked "download card".

**1. Turn on the access log** — Caddy does not log by default. Inside the site block:

```caddy
	log {
		output file /var/log/caddy/access.log {
			roll_size 20MiB
			roll_keep 10
			roll_keep_for 2160h
		}
	}
```

> ⚠️ **`sudo caddy validate` creates that file as root, and then the service cannot write to it.**
> Validating does not merely parse — it provisions the modules, and provisioning the file writer
> *creates the log file*. Run under `sudo` it lands as `root:root` mode `0600`, and the reload then
> fails with `open /var/log/caddy/access.log: permission denied` forever, no matter what the
> directory permissions say. The confusing part is that everything else looks correct: the folder is
> owned by `caddy`, and `sudo -u caddy touch` succeeds — because it creates a *different* file.
> Make `chown -R caddy:caddy /var/log/caddy` a permanent step between `validate` and `reload`.

A `LogsDirectory=caddy` drop-in is worth adding anyway (systemd then creates the directory with the
right owner and adds it to the sandbox's writable paths), but it is hygiene, not the fix above.

**2. Teach GoAccess the format.** Caddy logs JSON; GoAccess needs the field names spelled out. This
matches Caddy 2.11:

```
log-format {"ts":"%x","request":{"client_ip":"%h","proto":"%H","method":"%m","host":"%v","uri":"%U","headers":{"User-Agent":["%u"],"Referer":["%R"]}},"size":"%b","status":"%s"}
date-format %s
time-format %s
anonymize-ip true
ignore-crawlers true
real-os true
```

The one thing that will not work out of the box: Caddy writes `"ts":1785478441.368`, a **fractional**
epoch, and `%s` wants whole seconds — `Token '…' doesn't match specifier '%x'`. Strip the decimals on
the way in rather than changing Caddy's time format, so the log keeps its full precision on disk for
when you need to line a request up against an error:

```bash
cat /var/log/caddy/access.log /var/log/caddy/access-*.log 2>/dev/null \
  | sed 's/"ts":\([0-9]*\)\.[0-9]*/"ts":\1/' \
  | goaccess - -p /etc/goaccess/caddy.conf -o /var/www/stats/new-index.html
```

GoAccess rejects an output filename whose extension is not `.html`, `.json` or `.csv` — so the
temporary file for an atomic write must still end in `.html`, and must sit in the destination
directory, since `mv` is only atomic within one filesystem. A `systemd` timer on `OnCalendar=*:0/15`
regenerates it.

**3. Serve it on its own subdomain, not on a path.** `stats.example.org`, with `basic_auth` (hash it
with `caddy hash-password`) and its own site block appended to the Caddyfile — so the block that
serves the site is not touched at all. The subdomain is not cosmetic: the site is a PWA, and its
service worker intercepts every same-origin request. On a path, `/stats` would be served
stale-while-revalidate — showing a cached dashboard when the whole point is that it refreshes — and
would fall back to the site's own home page whenever the network hiccuped. A different origin is
outside the service worker's reach by its first rule.

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
- **No client-side analytics, no cookies, no third-party scripts.** Nothing is loaded from another
  origin and nothing tracks the reader across the web. The only things stored *in the browser* are
  the reader's own choices, in `localStorage`: language, theme, whether the tour has been seen, and
  the viewer's filters. The *server* keeps ordinary access logs — see
  [traffic statistics](#traffic-statistics) — which is why that sentence says "client-side": no
  consent banner is needed, but the claim has to stay exact.
