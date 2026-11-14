// node --test src/viewer/section.test.ts   (npm test)
import { test } from "node:test";
import assert from "node:assert/strict";
import { chip, clampTo, cutForFinding, deckBelow, faceDir, frameAt, keeps, nearSideFlip, plane, readout, sliceTile, snap, step, xOfFrame, type Box, type Cut } from "./section.ts";

const DECK5 = { frame0_x: 0, spacing_m: 0.8 };                    // Fr 120 at x = 96 (make_deck.py)
const D5BOX: Box = [[95.975, -13.5, 14.488], [172, 13.5, 17.3]];
const RCRV = { frame0_x: -62.416, spacing_m: 1.0 };               // no frame grid: metres from the aft end
const RBOX: Box = [[-62.416, -10.706, -1.362], [4.292, 8.654, 27]];
const DECKS = [{ deck: 1, z: 2.4 }, { deck: 2, z: 5.6 }, { deck: 3, z: 8.9 }];

test("frames map both ways on the deck5 grid and on metres-from-aft", () => {
  assert.equal(frameAt(96, DECK5), 120);
  assert.equal(xOfFrame(152, DECK5), 121.60000000000001);
  assert.equal(readout("cross", xOfFrame(152, DECK5), DECK5, [], D5BOX).main, "Fr 152");
  assert.equal(readout("cross", -62.416 + 45, RCRV, [], RBOX).main, "Fr 45");
  assert.equal(readout("cross", -62.416 + 45, RCRV, [], RBOX).sub, "45.0 m from aft end");
  assert.equal(readout("cross", 121.9, DECK5, [], D5BOX).main, "Fr 152 + 0.30 m");
  assert.equal(readout("cross", 121.3, DECK5, [], D5BOX).main, "Fr 152 − 0.30 m");
});

test("longitudinal and deck readouts", () => {
  assert.equal(readout("long", 3.2, DECK5, [], D5BOX).main, "3.2 m PS of CL");
  assert.equal(readout("long", -4.04, DECK5, [], D5BOX).main, "4.0 m SB of CL");
  assert.equal(readout("long", 0.01, DECK5, [], D5BOX).main, "On CL");
  assert.equal(readout("deck", 7.1, RCRV, DECKS, RBOX).main, "Deck 2 + 1.5 m");
  assert.equal(readout("deck", 0.5, RCRV, DECKS, RBOX).main, "1.9 m above keel");
  assert.equal(deckBelow(8.9, DECKS)?.deck, 3);
  assert.equal(chip({ kind: "long", pos: -2, flip: false }, DECK5, [], D5BOX), "2.0 m SB of CL");
});

test("plane keeps the low side unflipped, the high side flipped (three.js: n·p + c >= 0 kept)", () => {
  const c: Cut = { kind: "cross", pos: 120, flip: false };
  assert.deepEqual(plane(c), { normal: [-1, 0, 0], constant: 120 });
  assert.ok(keeps(c, [100, 0, 0]) && !keeps(c, [130, 0, 0]));
  assert.ok(keeps({ ...c, flip: true }, [130, 0, 0]) && !keeps({ ...c, flip: true }, [100, 0, 0]));
  const d: Cut = { kind: "deck", pos: 16, flip: false };
  assert.ok(keeps(d, [0, 0, 15]) && !keeps(d, [0, 0, 17]));          // deck plan: what is below stays
  assert.ok(keeps({ kind: "long", pos: 2, flip: true }, [0, 3, 0]));
});

test("cut removes the side the camera is on, and the camera then faces the cut from that side", () => {
  for (const [kind, cam] of [["cross", [200, 0, 0]], ["cross", [50, 0, 0]], ["long", [0, -40, 5]], ["deck", [0, 0, 80]]] as const) {
    const pos = kind === "cross" ? 120 : kind === "long" ? 1 : 16;
    const c: Cut = { kind, pos, flip: nearSideFlip(kind, pos, [...cam]) };
    assert.ok(!keeps(c, [...cam]), `${kind}: the camera side is cut away`);
    const d = faceDir(c), a = { cross: 0, long: 1, deck: 2 }[kind];
    assert.equal(Math.sign(d[a]), Math.sign(cam[a] - pos), `${kind}: camera ends up on the removed side`);
  }
});

test("snap, step one frame / 0.1 m, Shift = 10, clamp to the model", () => {
  assert.equal(snap("cross", 121.9, DECK5), xOfFrame(152, DECK5));
  assert.equal(snap("long", 3.24, DECK5), 3.2);
  assert.equal(frameAt(step("cross", xOfFrame(152, DECK5), 1, DECK5, D5BOX), DECK5), 153);
  assert.equal(Math.round(frameAt(step("cross", xOfFrame(152, DECK5), -1, DECK5, D5BOX, true), DECK5)), 142);
  assert.equal(step("long", 3.2, 1, DECK5, D5BOX), 3.3);
  const last = step("cross", xOfFrame(215, DECK5), 1, DECK5, D5BOX);   // Fr 215 = 172 m = the forward end
  assert.ok(last <= 172 && frameAt(last, DECK5) === 214, `stays inside: Fr ${frameAt(last, DECK5)}`);
  assert.equal(clampTo("deck", 40, RBOX), 27);
});

test("section at finding: deck plan through a room, cross section through a part", () => {
  assert.deepEqual(cutForFinding({ evidence: { bbox: [120, -2, 130, 2], z: 14.5 } }, DECK5), { kind: "deck", pos: 16, flip: false });
  const c = cutForFinding({ evidence: null, elementBox: [-20.3, -1, 2, -19.1, 1, 3] }, RCRV)!;
  assert.equal(c.kind, "cross"); assert.equal(frameAt(c.pos, RCRV), 43);
  assert.equal(cutForFinding({}, DECK5), null);
});

test("slice a quantised unit cube: x = 0.25 gives the 4 edges of a square, each tagged with its element", () => {
  // cube [0,1]^3 as 12 triangles, quantised with scale 1/65535 and offset 0; element 7 on every vertex
  const V = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];
  const F = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 3, 7, 6, 3, 6, 2, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5];
  const q = new Uint16Array(V.flatMap((v) => [...v.map((x) => x * 65535), 7]));
  const s = 1 / 65535;
  const { seg, elem } = sliceTile(q, 4, new Uint32Array(F), [s, s, s], [10, 20, 30], 0, 10.25);
  assert.equal(seg.length / 6, 8, "two triangles per side face cross the plane: 8 segments");
  assert.ok([...elem].every((e) => e === 7));
  for (let i = 0; i < seg.length; i += 3) {
    assert.ok(Math.abs(seg[i] - 10.25) < 1e-4, "every point lies on the plane");
    assert.ok(seg[i + 1] >= 20 - 1e-6 && seg[i + 1] <= 21 + 1e-6 && seg[i + 2] >= 30 - 1e-6 && seg[i + 2] <= 31 + 1e-6);
  }
  let len = 0;
  for (let i = 0; i < seg.length; i += 6) len += Math.hypot(seg[i + 3] - seg[i], seg[i + 4] - seg[i + 1], seg[i + 5] - seg[i + 2]);
  assert.ok(Math.abs(len - 4) < 1e-3, `outline is the 1 m square: ${len}`);
  assert.equal(sliceTile(q, 4, new Uint32Array(F), [s, s, s], [10, 20, 30], 0, 12).seg.length, 0, "plane outside: nothing");
});
