// W4 Model viewer: IFC from the engine rendered with That Open Engine (web-ifc + three.js); finding pins are
// screen-space HTML placed at each finding's evidence box. Load errors keep the list and offer reload.
import { useEffect, useRef, useState } from "react";
import * as OBC from "@thatopen/components";
import * as THREE from "three";
import { api, BASE, HDR, type Check, type Run } from "../api";
import { Loc, Pill } from "../components/ui";

type Pin = { c: Check; x: number; y: number; visible: boolean };

export default function Viewer({ rev, run, hvac, onOpen }: { rev: string; run: Run | null; hvac: Run | null; onOpen: (c: Check) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [err, setErr] = useState("");
  const [pins, setPins] = useState<Pin[]>([]);
  const [nonce, setNonce] = useState(0);
  const findings = [...(run?.findings ?? []), ...(hvac?.findings ?? [])];

  useEffect(() => {
    if (!host.current) return;
    let disposed = false;
    let timer = 0;
    const components = new OBC.Components();
    const worlds = components.get(OBC.Worlds);
    const world = worlds.create<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>();
    world.scene = new OBC.SimpleScene(components);
    world.renderer = new OBC.SimpleRenderer(components, host.current);
    world.camera = new OBC.SimpleCamera(components);
    components.init();
    world.scene.setup();
    (world.scene.three as THREE.Scene).background = new THREE.Color(getComputedStyle(host.current).getPropertyValue("--plan-bg").trim() || "#17191c");
    const loader = components.get(OBC.IfcLoader);
    let pts: { c: Check; v: THREE.Vector3 }[] = [];
    // IFC (x, y, z-up) -> three (x, z, -y), then calibrated against the loaded model's box (the loader may recentre)
    const place = (b: number[], box: THREE.Box3) => {
      const off = new THREE.Vector3(box.min.x - b[0], box.min.y - b[2], box.min.z + b[4]);
      pts = findings.filter((c) => c.evidence?.bbox).map((c) => {
        const [x0, y0, x1, y1] = c.evidence!.bbox!;
        const z = (c.evidence!.z ?? b[2]) + 1.4;
        return { c, v: new THREE.Vector3((x0 + x1) / 2 + off.x, z + off.y, -(y0 + y1) / 2 + off.z) };
      });
    };
    const update = () => {
      if (disposed || !host.current) return;
      const cam = world.camera.three as THREE.Camera;
      cam.updateMatrixWorld();
      const w = host.current.clientWidth, h = host.current.clientHeight;
      setPins(pts.map(({ c, v }) => {
        const p = v.clone().project(cam);
        return { c, x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, visible: p.z < 1 && Math.abs(p.x) < 1.1 && Math.abs(p.y) < 1.1 };
      }));
    };
    (async () => {
      try {
        loader.settings.autoSetWasm = false;
        loader.settings.wasm = { path: BASE + "wasm/", absolute: true };
        loader.settings.webIfc.COORDINATE_TO_ORIGIN = false;
        await loader.setup();
        const buf = new Uint8Array(await (await fetch(api.ifcUrl(rev), { headers: HDR })).arrayBuffer());
        const model = await loader.load(buf);
        if (disposed) return;
        world.scene.three.add(model);
        const box = new THREE.Box3().setFromObject(model);
        const info = await api.model();
        if (info.bounds) place(info.bounds, box);
        host.current?.setAttribute("data-box", JSON.stringify([box.min.toArray(), box.max.toArray(), info.bounds]));
        await world.camera.controls.fitToBox(box, false);
        await world.camera.controls.rotateTo(-0.35, 0.75, false);
        await world.camera.controls.fitToBox(box, false, { paddingTop: 2, paddingBottom: 2, paddingLeft: 2, paddingRight: 2 });
        world.camera.controls.addEventListener("update", update);
        timer = window.setInterval(update, 250);
        update();
        setState("ready");
      } catch (e) {
        setErr(String(e));
        setState("error");
      }
    })();
    return () => { disposed = true; window.clearInterval(timer); components.dispose(); };
  }, [rev, nonce, run?.revision]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: "minmax(0, 1fr) 320px" }}>
      <div className="viewer" ref={host}>
        {state === "loading" && <div className="sq-muted" style={{ position: "absolute", left: 16, top: 12 }}>Loading Deck 5 · Rev {rev}…</div>}
        {state === "error" && (
          <div className="sq-banner" style={{ position: "absolute", left: 16, top: 12, right: 16 }}>
            <div>Model did not load ({err}). The findings list still works. <button className="sq-btn is-sm" onClick={() => setNonce(nonce + 1)}>Reload</button></div>
          </div>
        )}
        {pins.filter((p) => p.visible).map((p) => (
          <button key={p.c.check_key} className={`sq-pin s-${p.c.status}`} style={{ left: p.x, top: p.y }} onClick={() => onOpen(p.c)}>
            <i className="sq-ico" />{p.c.id}
          </button>
        ))}
        <div className="sq-legend" style={{ position: "absolute", left: 12, bottom: 12 }}>
          <span className="ln"><i className="l-a60" />A-60</span><span className="ln"><i className="l-a0" />A-0</span>
          <span className="ln"><i className="l-b15" />B-15</span><span className="ln"><i className="l-b0" />B-0</span>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <div className="sq-label">Findings on this deck · {findings.length}</div>
        {findings.map((c) => (
          <button key={c.check_key} className="sq-row" style={{ textAlign: "left", background: "none", gridTemplateColumns: "108px minmax(0, 1fr)", justifyItems: "start" }} onClick={() => onOpen(c)}>
            <Pill s={c.status} />
            <span className="t"><span className="id">{c.id}</span>{c.title}</span>
            <span className="m"><Loc text={c.location.label} /></span>
          </button>
        ))}
      </div>
    </div>
  );
}
