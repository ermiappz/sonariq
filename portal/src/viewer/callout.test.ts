// node --test src/viewer/callout.test.ts   (npm test)
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { calloutContent, calloutText, placeCallout, strayNumbers } from "./callout.ts";

// one finding per rule and status from deck5_revB (engine output, see fixtures/)
const F = JSON.parse(fs.readFileSync(new URL("./fixtures/deck5_revB_findings.json", import.meta.url), "utf8"));
const by = (id: string) => F.find((c: any) => c.id === id);

test("callout text only repeats numbers of the finding (number guard)", () => {
  for (const c of F) {
    const t = calloutText(calloutContent(c));
    assert.deepEqual(strayNumbers(c, t), [], `${c.id}: ${t}`);
  }
  // the guard itself catches a typed number
  assert.deepEqual(strayNumbers(by("F-07"), "clear width 1,400 mm"), [1400]);
});

test("Is / Must be wording per finding kind", () => {
  const stair = calloutContent(by("F-07"));
  assert.equal(stair.is, "clear width 1,350 mm · " + by("F-07").element.name);
  assert.equal(stair.mustBe, "at least 1,380 mm");
  assert.match(stair.formula!, /= 1,380 mm$/);
  assert.equal(stair.where, "FSS Code Ch.13 §2.1.2 · Stair 3B · Decks 4–7");
  assert.equal(calloutContent(by("F-08")).is, "dead end 4.2 m deep");
  assert.equal(calloutContent(by("F-08")).mustBe, "at most as deep as it is wide: 1.2 m");
  assert.equal(calloutContent(by("F-01")).mustBe, "at least A-60");
  assert.match(calloutContent(by("U-01")).is, /^not in the model: Pset_DoorCommon\.FireRating/);
  assert.equal(calloutContent(by("H-01")).mustBe, "fire damper present");
  assert.equal(calloutContent(by("W-01")).mustBe, "at least 915 mm (36 in)");
});

test("placement: beside the element, inside the view, never over the element", () => {
  const view = { w: 1000, h: 700 }, size = { w: 300, h: 200 };
  const over = (p: { x: number; y: number }, r: any) => p.x < r.x1 && p.x + size.w > r.x0 && p.y < r.y1 && p.y + size.h > r.y0;
  for (const r of [{ x0: 400, y0: 300, x1: 460, y1: 360 }, { x0: 800, y0: 100, x1: 990, y1: 600 }, { x0: 10, y0: 10, x1: 900, y1: 450 }]) {
    const p = placeCallout([(r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2], r, size, view);
    assert.ok(!over(p, r), JSON.stringify({ r, p }));
    assert.ok(p.x >= 0 && p.y >= 0 && p.x + size.w <= view.w && p.y + size.h <= view.h);
    assert.ok(p.lead[0] >= p.x && p.lead[0] <= p.x + size.w && p.lead[1] >= p.y && p.lead[1] <= p.y + size.h);
  }
  assert.equal(placeCallout([500, 350], { x0: 400, y0: 300, x1: 600, y1: 400 }, size, view).side, "right");
  // element fills the view: a corner, away from the anchor
  assert.equal(placeCallout([100, 100], { x0: 0, y0: 0, x1: 1000, y1: 700 }, size, view).side, "corner");
});
