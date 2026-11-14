// Spike B1, option 1: one full-geometry IFC (to_ifc.py) -> one .frag with @thatopen/fragments IfcImporter (web-ifc, node).
// usage: node frag_convert.mjs <in.ifc> <out.frag>   (one process per file so peak memory is per file)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as FRAGS from '@thatopen/fragments';

const [src, dst] = process.argv.slice(2);
const here = path.dirname(fileURLToPath(import.meta.url));
const importer = new FRAGS.IfcImporter();
importer.wasm = { path: path.join(here, 'node_modules/web-ifc/'), absolute: true };   // own disk, no CDN
importer.parseOnce = true;                      // one web-ifc instance for geometry + properties (halves memory)
const fd = fs.openSync(src, 'r');
const t0 = Date.now();
let peak = 0; const timer = setInterval(() => { peak = Math.max(peak, process.memoryUsage().rss); }, 250);
const res = { src: path.basename(src), inBytes: fs.statSync(src).size };
try {
  const out = await importer.process({
    readFromCallback: true,
    readCallback: (offset, size) => { const b = new Uint8Array(size); const n = fs.readSync(fd, b, 0, size, offset); return n === size ? b : b.slice(0, n); },
  });
  fs.writeFileSync(dst, out);
  res.outBytes = out.length;
} catch (e) { res.error = String(e && e.stack || e).slice(0, 600); }
clearInterval(timer);
res.seconds = (Date.now() - t0) / 1000;
res.peakRssMB = Math.round(Math.max(peak, process.memoryUsage().rss) / 1048576);
console.log(JSON.stringify(res));
process.exit(res.error ? 1 : 0);
