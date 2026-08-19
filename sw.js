/* The Living Arkham — service worker (PWA offline cache).

   install : precache only the light SHELL (sw-shell.json, ~1.4 MB) — css/js/fonts/icons +
             registries + every language's UI. The app opens offline in any language; nothing
             heavy is downloaded unless the user asks.
   runtime : shell/text  -> stale-while-revalidate (instant + self-updating; new versions still
                            reach the user next load). Reading a page caches its text too.
             card images -> cache-first (immutable per URL; cached as viewed).
   message : the footer "use offline" panel drives bulk downloads and reads status:
               {type:'cache', what:'rules'} -> cache all rules text (sw-text.json).
               {type:'cache', what:'all'}   -> rules text + every image (sw-assets.json).
               {type:'status'}              -> how much of each is already cached.
             Progress + completion are posted back to the calling page.

   BUMP SW_VERSION on every release (see tools/other/instructions.md §7): it renames the shell
   cache, so activate() drops the old one and the new shell/text is served. */

const SW_VERSION = '1.4.0';
const SHELL = 'tla-shell-' + SW_VERSION;   // shell + read/downloaded text, replaced each version
// Images are cache-first and, being immutable per URL, are kept across versions — a plain
// SW_VERSION bump does NOT drop them, so offline images survive text-only releases. Bump
// MEDIA_VERSION instead whenever a cached image's CONTENT changes at the SAME URL (a fixed card
// or back): it renames the media cache, so activate() drops the stale one and the corrected
// images are re-fetched fresh. (Raised to 2 in 1.2.2, after the Scorched Earth + back fixes.)
const MEDIA_VERSION = '2';
const MEDIA = 'tla-media-' + MEDIA_VERSION;

function isMedia(path) {
  return /\/assets\/(ub|taboo|img|products|faqsets|icons)\//.test(path)
      || /\/assets\/general_banner/.test(path);
}

self.addEventListener('install', function (e) {
  e.waitUntil((async function () {
    const cache = await caches.open(SHELL);
    let urls = ['./'];
    try { urls = await (await fetch('sw-shell.json', { cache: 'no-cache' })).json(); }
    catch (err) { /* fall back to just the shell entry */ }
    await Promise.all(urls.map(function (u) {
      return cache.add(new Request(u, { cache: 'no-cache' })).catch(function () {});
    }));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', function (e) {
  e.waitUntil((async function () {
    const keep = [SHELL, MEDIA];
    for (const k of await caches.keys()) {
      if (k.indexOf('tla-') === 0 && keep.indexOf(k) < 0) await caches.delete(k);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', function (e) {
  const req = e.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (err) { return; }
  if (url.origin !== self.location.origin) return;   // never touch cross-origin

  // Usage beacons (app.js -> ping()). Never intercept and never cache: the
  // stale-while-revalidate branch below would serve a cached 204 and the
  // beacon would stop reaching the server after the first navigation — the
  // panel would flatline silently, which is worse than erroring.
  if (url.pathname.indexOf('/e/') === 0) return;

  if (req.mode === 'navigate') {
    e.respondWith((async function () {
      try { return await fetch(req); }
      catch (err) {
        return (await caches.match('./')) || (await caches.match('index.html')) || Response.error();
      }
    })());
    return;
  }

  if (isMedia(url.pathname)) {
    e.respondWith((async function () {
      const cache = await caches.open(MEDIA);
      const hit = await cache.match(req);               // only THIS version's media cache
      if (hit) return hit;
      try {
        // 'no-cache' on the miss: revalidate with the server so a re-fetch after a MEDIA_VERSION
        // bump gets the corrected bytes, not a stale copy from the browser's own HTTP cache.
        const res = await fetch(req, { cache: 'no-cache' });
        if (res && res.ok) cache.put(req, res.clone());
        return res;
      } catch (err) { return hit || Response.error(); }
    })());
    return;
  }

  // shell + text -> stale-while-revalidate (also caches text as you read it)
  e.respondWith((async function () {
    const cache = await caches.open(SHELL);
    const hit = await cache.match(req);
    const net = fetch(req).then(function (res) {
      if (res && res.ok) cache.put(req, res.clone());
      return res;
    }).catch(function () { return null; });
    return hit || (await net) || Response.error();
  })());
});

// ---- bulk download for offline (footer "use offline" panel) ----
function post(client, msg) { if (client) client.postMessage(msg); }

async function fetchList(u) {
  try { return await (await fetch(u, { cache: 'no-cache' })).json(); }
  catch (err) { return []; }
}

async function cacheBulk(what, client) {
  // 'rules' = text only; 'all' = text + every image
  const jobs = what === 'all'
    ? [['sw-text.json', SHELL], ['sw-assets.json', MEDIA]]
    : [['sw-text.json', SHELL]];
  const stages = [];
  for (const j of jobs) stages.push({ list: await fetchList(j[0]), cache: await caches.open(j[1]) });
  const total = stages.reduce(function (n, s) { return n + s.list.length; }, 0);
  let done = 0;
  const CONC = 6;
  for (const stage of stages) {
    const chunks = [];
    for (let i = 0; i < CONC; i++) chunks.push(stage.list.filter(function (_, j) { return j % CONC === i; }));
    await Promise.all(chunks.map(async function (slice) {
      for (const url of slice) {
        try {
          if (!(await stage.cache.match(url))) {
            const res = await fetch(url, { cache: 'no-cache' });
            if (res && res.ok) await stage.cache.put(url, res.clone());
          }
        } catch (err) { /* skip one bad file, keep going */ }
        done++;
        if (done % 10 === 0) post(client, { type: 'cache-progress', what: what, done: done, total: total });
      }
    }));
  }
  post(client, { type: 'cache-done', what: what, ok: true, done: done, total: total });
}

async function cacheStatus(client) {
  const out = { type: 'status' };
  const specs = [['rules', 'sw-text.json', SHELL], ['assets', 'sw-assets.json', MEDIA]];
  for (const spec of specs) {
    const list = await fetchList(spec[1]);
    const cache = await caches.open(spec[2]);
    const have = new Set((await cache.keys()).map(function (r) {
      return new URL(r.url).pathname.replace(/^\//, '');
    }));
    let n = 0;
    for (const u of list) if (have.has(u.replace(/^\//, ''))) n++;
    out[spec[0]] = { have: n, total: list.length };
  }
  post(client, out);
}

self.addEventListener('message', function (e) {
  const d = e.data;
  if (!d) return;
  if (d.type === 'cache') e.waitUntil(cacheBulk(d.what === 'all' ? 'all' : 'rules', e.source));
  else if (d.type === 'status') e.waitUntil(cacheStatus(e.source));
});
