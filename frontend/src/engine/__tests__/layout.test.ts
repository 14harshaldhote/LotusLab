import { describe, expect, it } from "vitest";

import { LeafLayout } from "../layout";
import { skyAt } from "../sky";

describe("LeafLayout", () => {
  const layout = new LeafLayout(300, 1);

  it("is deterministic for a seed", () => {
    expect(new LeafLayout(300, 1).leaves).toEqual(layout.leaves);
  });

  it("keeps every leaf inside the unit disk", () => {
    for (const l of layout.leaves) expect(Math.hypot(l.x, l.y) + l.r).toBeLessThanOrEqual(1.0001);
  });

  it("leaf count grows monotonically with cover", () => {
    let prev = -1;
    for (let c = 0; c <= 1.0001; c += 0.05) {
      const k = layout.countFor(c);
      expect(k).toBeGreaterThanOrEqual(prev);
      prev = k;
    }
    expect(layout.countFor(0)).toBe(0);
    expect(layout.countFor(5)).toBe(300);
  });
});

describe("skyAt", () => {
  it("is dark at night and bright at noon", () => {
    expect(skyAt(-30, 0).ambient).toBeLessThan(0.2);
    expect(skyAt(60, 0).ambient).toBeCloseTo(1, 5);
    expect(skyAt(-30, 0).starOpacity).toBe(1);
    expect(skyAt(60, 0).starOpacity).toBe(0);
  });

  it("clouds dim the scene and hide the stars", () => {
    expect(skyAt(60, 100).ambient).toBeLessThan(skyAt(60, 0).ambient);
    expect(skyAt(-30, 100).starOpacity).toBe(0);
  });
});
