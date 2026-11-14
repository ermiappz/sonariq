// Static server for the spike pages: /data/* -> data/rcrv/spike_b1, everything else -> spikes/b1. Own origin only.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const data = path.resolve(here, '../../data/rcrv/spike_b1');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.wasm': 'application/wasm' };
http.createServer((req, res) => {
  const p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const root = p.startsWith('/data/') ? data : here;
  const file = path.join(root, p.startsWith('/data/') ? p.slice(5) : p);
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404).end(); return; }
  res.writeHead(200, { 'content-type': types[path.extname(file)] || 'application/octet-stream', 'content-length': fs.statSync(file).size });
  fs.createReadStream(file).pipe(res);
}).listen(Number(process.argv[2] || 8899), '127.0.0.1');
