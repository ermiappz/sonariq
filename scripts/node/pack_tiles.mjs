// Meshopt-compress every raw tile from engine/sonariq/pipeline/tiles.py (EXT_meshopt_compression) and run the
// integrity check: decode each compressed tile again and compare vertices and triangles with the raw tile.
// usage: node pack_tiles.mjs <raw dir> <out dir>   -> prints one JSON line; exit 2 on any mismatch
import fs from 'node:fs';
import path from 'node:path';
import { MeshoptEncoder, MeshoptDecoder } from 'meshoptimizer';

const [src, dst] = process.argv.slice(2);
await MeshoptEncoder.ready; await MeshoptDecoder.ready;
fs.mkdirSync(dst, { recursive: true });
const t0 = Date.now();
const total = { files: 0, raw: 0, packed: 0, vertexMismatch: 0, triangleMismatch: 0 };

// order-independent checksum over triangles of (position, element id) records
function triSum(v32, idx, map) {
  let sum = 0, xor = 0;
  for (let i = 0; i < idx.length; i += 3) {
    let s = 0, x = 0;
    for (let k = 0; k < 3; k++) {
      const j = (map ? map[idx[i + k]] : idx[i + k]) * 2;
      const h = Math.imul(v32[j] ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(v32[j + 1] + 0x7f4a7c15, 0xc2b2ae35);
      s = (s + h) | 0; x ^= Math.imul(h, 0x27d4eb2f);
    }
    const t = Math.imul(s, 0x165667b1) ^ x;
    sum = (sum + t) | 0; xor ^= Math.imul(t, 0x9e3779b1);
  }
  return [sum, xor];
}

for (const name of fs.readdirSync(src).filter(f => f.endsWith('.glb'))) {
  const buf = fs.readFileSync(path.join(src, name));
  const jl = buf.readUInt32LE(12);
  const js = JSON.parse(buf.subarray(20, 20 + jl).toString());
  const bin = buf.subarray(20 + jl + 8);
  const nv = js.accessors[0].count, ni = js.accessors[2].count;
  const srcV = new Uint32Array(new Uint8Array(bin.subarray(0, nv * 8)).buffer);     // 8-byte vertex = 2 x u32
  const srcI = new Uint32Array(new Uint8Array(bin.subarray(nv * 8, nv * 8 + ni * 4)).buffer);
  const want = triSum(srcV, srcI);

  const idx = srcI.slice();
  const [remap, unique] = MeshoptEncoder.reorderMesh(idx, true, false);
  const v = new Uint32Array(unique * 2);
  for (let i = 0; i < nv; i++) if (remap[i] !== 0xffffffff) { v[remap[i] * 2] = srcV[i * 2]; v[remap[i] * 2 + 1] = srcV[i * 2 + 1]; }
  const cv = MeshoptEncoder.encodeVertexBuffer(new Uint8Array(v.buffer), unique, 8);
  const ci = MeshoptEncoder.encodeIndexBuffer(new Uint8Array(idx.buffer), ni, 4);

  // integrity: decode what we just encoded, compare with the source tile
  const dv = new Uint8Array(unique * 8), di = new Uint8Array(ni * 4);
  MeshoptDecoder.decodeVertexBuffer(dv, unique, 8, cv);
  MeshoptDecoder.decodeIndexBuffer(di, ni, 4, ci);
  const dV = new Uint32Array(dv.buffer), dI = new Uint32Array(di.buffer);
  for (let i = 0; i < nv; i++) if (remap[i] !== 0xffffffff && (dV[remap[i] * 2] !== srcV[i * 2] || dV[remap[i] * 2 + 1] !== srcV[i * 2 + 1])) total.vertexMismatch++;
  const got = triSum(dV, dI);
  if (got[0] !== want[0] || got[1] !== want[1]) total.triangleMismatch++;

  const pad = n => (4 - n % 4) % 4;
  const iOff = cv.length + pad(cv.length), binLen = iOff + ci.length + pad(ci.length);
  const ext = 'EXT_meshopt_compression';
  js.extensionsUsed.push(ext); js.extensionsRequired.push(ext);
  js.buffers = [{ byteLength: binLen }, { byteLength: unique * 8 + ni * 4, extensions: { [ext]: { fallback: true } } }];
  js.bufferViews = [
    { buffer: 1, byteOffset: 0, byteLength: unique * 8, byteStride: 8, target: 34962,
      extensions: { [ext]: { buffer: 0, byteOffset: 0, byteLength: cv.length, byteStride: 8, mode: 'ATTRIBUTES', count: unique } } },
    { buffer: 1, byteOffset: unique * 8, byteLength: ni * 4, target: 34963,
      extensions: { [ext]: { buffer: 0, byteOffset: iOff, byteLength: ci.length, byteStride: 4, mode: 'TRIANGLES', count: ni } } }];
  js.accessors[0].count = js.accessors[1].count = unique;
  let jb = Buffer.from(JSON.stringify(js)); jb = Buffer.concat([jb, Buffer.alloc(pad(jb.length), 0x20)]);
  const out = Buffer.alloc(12 + 8 + jb.length + 8 + binLen);
  out.write('glTF', 0); out.writeUInt32LE(2, 4); out.writeUInt32LE(out.length, 8);
  out.writeUInt32LE(jb.length, 12); out.write('JSON', 16); jb.copy(out, 20);
  let o = 20 + jb.length; out.writeUInt32LE(binLen, o); out.write('BIN\0', o + 4); o += 8;
  Buffer.from(cv).copy(out, o); Buffer.from(ci).copy(out, o + iOff);
  fs.writeFileSync(path.join(dst, name), out);
  total.files++; total.raw += buf.length; total.packed += out.length;
}
total.seconds = (Date.now() - t0) / 1000;
console.log(JSON.stringify(total));
if (total.vertexMismatch || total.triangleMismatch) process.exit(2);
