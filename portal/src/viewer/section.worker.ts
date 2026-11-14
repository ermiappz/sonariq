// Section edges off the main thread (DECISIONS M5): keeps a copy of each tile it was sent, slices on request.
import { sliceTile } from "./section";

type T = { q: Uint16Array; idx: Uint32Array | Uint16Array; scale: number[]; offset: number[] };
const tiles = new Map<string, T>();

self.onmessage = (e: MessageEvent) => {
  const m = e.data;
  if (m.type === "tile") tiles.set(m.key, m.tile);
  else if (m.type === "drop") tiles.delete(m.key);
  else if (m.type === "slice") {
    const out: { key: string; seg: Float32Array; elem: Uint16Array }[] = [];
    const transfer: ArrayBuffer[] = [];
    for (const key of m.keys as string[]) {
      const t = tiles.get(key);
      if (!t) continue;
      const r = sliceTile(t.q, 4, t.idx, t.scale, t.offset, m.axis, m.value);
      if (!r.seg.length) continue;
      out.push({ key, ...r });
      transfer.push(r.seg.buffer as ArrayBuffer, r.elem.buffer as ArrayBuffer);
    }
    (self as unknown as Worker).postMessage({ type: "slice", id: m.id, out }, transfer);
  }
};
