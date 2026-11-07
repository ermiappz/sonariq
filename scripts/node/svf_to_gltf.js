#!/usr/bin/env node
// SonarIQ wrapper around svf-utils (its CLI has a top-level-await bug under Node 26).
// Usage: node svf_to_gltf.js <urn> <outFolder>
// Writes <out>/<viewGuid>/output.gltf (+ .bin) per 3D SVF viewable and <out>/properties.jsonl.
const path = require('path');
const fs = require('fs');
const { Scopes } = require('@aps_sdk/authentication');
const { ModelDerivativeClient } = require('@aps_sdk/model-derivative');
const { SVFReader, GLTFWriter, TwoLeggedAuthenticationProvider } = require('svf-utils');

async function main() {
  const [urn, out] = process.argv.slice(2);
  const { APS_CLIENT_ID, APS_CLIENT_SECRET, APS_REGION } = process.env;
  const auth = new TwoLeggedAuthenticationProvider(APS_CLIENT_ID, APS_CLIENT_SECRET);
  const md = new ModelDerivativeClient();
  const accessToken = await auth.getToken([Scopes.ViewablesRead]);
  const manifest = await md.getManifest(urn, { accessToken, region: APS_REGION });
  const svfs = [];
  (function walk(d) {
    if (d.type === 'resource' && d.role === 'graphics' && d.mime === 'application/autodesk-svf') svfs.push(d);
    for (const c of d.children || []) walk(c);
  })({ children: manifest.derivatives });
  console.log(`found ${svfs.length} SVF viewables`);
  const options = { deduplicate: true, skipUnusedUvs: true, ignoreLineGeometry: true, ignorePointGeometry: true,
                    log: console.log };
  fs.mkdirSync(out, { recursive: true });
  let propsWritten = false;
  for (const d of svfs) {
    console.log('converting', d.guid);
    const reader = await SVFReader.FromDerivativeService(urn, d.guid, auth);
    if (!propsWritten) {
      const db = await reader.getPropertyDb();
      const n = db._offsets.length - 1;
      const fd = fs.openSync(path.join(out, 'properties.jsonl'), 'w');
      for (let id = 1; id < n; id++) {
        const props = [];
        let name = null, parent = null;
        for (const p of db.enumerateProperties(id)) {
          if (p.category === '__name__') name = p.value;
          else if (p.category === '__parent__') parent = p.value;
          else if (p.category && p.category.startsWith('__')) continue;
          else props.push([p.category, p.name, p.value]);
        }
        fs.writeSync(fd, JSON.stringify({ dbid: id, name, parent, ext: db._ids[id], props }) + '\n');
      }
      fs.closeSync(fd);
      propsWritten = true;
      console.log(`properties.jsonl: ${n - 1} objects`);
    }
    const scene = await reader.read({ log: console.log });
    const writer = new GLTFWriter(options);
    await writer.write(scene, path.join(out, d.guid));
    console.log('wrote', d.guid);
  }
  console.log('DONE');
}
main().catch(e => { console.error(e); process.exit(1); });
