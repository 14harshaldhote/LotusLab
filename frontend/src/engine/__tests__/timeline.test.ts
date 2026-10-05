import { describe, expect, it } from "vitest";

import type { TimelinePayload } from "../../api/types";
import { Timeline, localParts, phaseOf } from "../timeline";

function payload(n = 49): TimelinePayload {
  const t = Array.from({ length: n }, (_, i) => i);
  // sun elevation: a sine wave with 24 h period, crossing the horizon twice a day
  const elev = t.map((i) => 40 * Math.sin(((i - 6) / 24) * 2 * Math.PI));
  const rain = t.map((i) => (i >= 10 && i < 13 ? 2 : 0));
  let cum = 0;
  const rainM3 = rain.map((r) => r * 0.2);
  return {
    t0: 1000,
    dt: 3600,
    n,
    phase: elev.map(phaseOf),
    columns: {
      depth_m: t.map((i) => 1 + i * 0.01),
      sun_elevation_deg: elev,
      precipitation_mm: rain,
      rain_m3: rainM3,
      cum_rain_m3: rainM3.map((v) => (cum += v)),
    },
  };
}

describe("Timeline", () => {
  const tl = new Timeline(payload());

  it("returns stored rows exactly at grid points", () => {
    expect(tl.value("depth_m", 1000 + 5 * 3600)).toBeCloseTo(1.05, 12);
  });

  it("interpolates linearly between rows", () => {
    expect(tl.value("depth_m", 1000 + 5.5 * 3600)).toBeCloseTo(1.055, 12);
  });

  it("clamps outside the range", () => {
    expect(tl.value("depth_m", -1e9)).toBe(1);
    expect(tl.value("depth_m", 1e12)).toBeCloseTo(1.48, 12);
  });

  it("sample includes every column and a phase", () => {
    const s = tl.sample(1000 + 12 * 3600);
    expect(Object.keys(s)).toEqual(expect.arrayContaining(["depth_m", "sun_elevation_deg", "phase", "time"]));
    expect(s.phase).toBe(3);
  });

  it("uses prefix sums for flux totals in either order", () => {
    const a = 1000;
    const b = 1000 + 20 * 3600;
    expect(tl.between("rain_m3", a, b)).toBeCloseTo(1.2, 9);
    expect(tl.between("rain_m3", b, a)).toBeCloseTo(1.2, 9);
  });

  it("finds sunrise and sunset crossings in order", () => {
    const kinds = tl.events.map((e) => e.kind);
    expect(kinds.slice(0, 3)).toEqual(["sunrise", "sunset", "sunrise"]);
    const sunrise = tl.nextEvent(1000, "sunrise")!;
    expect(sunrise).toBeGreaterThan(1000 + 5 * 3600);
    expect(sunrise).toBeLessThan(1000 + 6 * 3600);
    expect(tl.nextEvent(sunrise, "sunrise")!).toBeCloseTo(sunrise + 24 * 3600, 6);
    expect(tl.nextEvent(tl.tEnd, "sunrise")).toBeNull();
  });

  it("finds the next rain start", () => {
    expect(tl.nextRain(1000)).toBe(1000 + 9 * 3600);
    expect(tl.nextRain(1000 + 20 * 3600)).toBeNull();
  });

  it("rejects malformed payloads", () => {
    const p = payload();
    p.columns.depth_m = [1, 2];
    expect(() => new Timeline(p)).toThrow();
  });
});

describe("localParts", () => {
  it("formats in the location's offset", () => {
    // 2025-07-01T00:00Z at UTC+5:30
    expect(localParts(1751328000, 19800)).toMatchObject({ date: "2025-07-01", time: "05:30" });
  });
});
