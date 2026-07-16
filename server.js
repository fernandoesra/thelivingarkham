#!/usr/bin/env node
/* Zero-dependency static dev server for local preview.
   Usage: node server.js  [port]   (default 8080)
   Serves this folder exactly like GitHub Pages would. */
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PORT = Number(process.argv[2] || process.env.PORT || 8080);

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff2': 'font/woff2',
  '.woff': 'font/woff', '.ttf': 'font/ttf', '.pdf': 'application/pdf',
  '.map': 'application/json',
};

const server = http.createServer((req, res) => {
  let urlPath = decodeURIComponent((req.url || '/').split('?')[0].split('#')[0]);
  if (urlPath === '/' || urlPath === '') urlPath = '/index.html';
  // prevent path traversal
  const filePath = path.normalize(path.join(ROOT, urlPath));
  if (!filePath.startsWith(ROOT)) { res.writeHead(403); return res.end('Forbidden'); }
  fs.stat(filePath, (err, st) => {
    let fp = filePath;
    if (!err && st.isDirectory()) fp = path.join(filePath, 'index.html');
    fs.readFile(fp, (e, data) => {
      if (e) { res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }); return res.end('404 Not Found: ' + urlPath); }
      res.writeHead(200, {
        'Content-Type': MIME[path.extname(fp).toLowerCase()] || 'application/octet-stream',
        // Never cache while developing: after `python tools/ingest.py` you must see
        // the language you just built, not the registry the browser remembers.
        'Cache-Control': 'no-store, max-age=0',
      });
      res.end(data);
    });
  });
});

server.listen(PORT, () => {
  console.log('\n  The Living Arkham — dev server');
  console.log('  ▶  http://localhost:' + PORT + '/\n  (Ctrl+C to stop)\n');
});
