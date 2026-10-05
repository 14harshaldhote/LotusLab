/**
 * Deterministic lotus leaf layout.
 *
 * Leaves are generated once per seed in the unit disk and ordered so that the first
 * k leaves always form a plausible colony spreading out from a few founding points.
 * Rendering cover c then means "show the first k leaves", with k found by binary
 * search over the cumulative leaf area: O(log N) per frame, no re-layout, and no
 * flicker because leaf positions never change.
 */

export interface Leaf {
  x: number; // unit disk coordinates
  y: number;
  r: number;
  rot: number; // degrees, position of the leaf notch
  flower: boolean;
}

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class LeafLayout {
  readonly leaves: Leaf[];
  private readonly cumArea: Float64Array; // fraction of the disk covered by the first k leaves

  constructor(count = 420, seed = 42, colonies = 3) {
    const rnd = mulberry32(seed);
    const centres = Array.from({ length: colonies }, () => polar(rnd, 0.75));
    const candidates = Array.from({ length: count }, () => {
      const r = 0.04 + rnd() * 0.035;
      const [x, y] = polar(rnd, 0.99 - r); // whole pad stays on the water
      const d = Math.min(...centres.map(([cx, cy]) => Math.hypot(x - cx, y - cy)));
      return {
        x,
        y,
        r,
        rot: rnd() * 360,
        flower: rnd() < 0.12,
        priority: d + rnd() * 0.18,
      };
    });
    candidates.sort((a, b) => a.priority - b.priority);
    this.leaves = candidates.map(({ x, y, r, rot, flower }) => ({ x, y, r, rot, flower }));
    this.cumArea = new Float64Array(count + 1);
    for (let i = 0; i < count; i++) this.cumArea[i + 1] = this.cumArea[i] + this.leaves[i].r ** 2;
  }

  /** Number of leaves whose summed area best matches a cover fraction of the water. */
  countFor(coverOfWater: number, overlap = 1.35): number {
    const target = Math.max(0, coverOfWater) * overlap;
    if (target >= this.cumArea[this.cumArea.length - 1]) return this.leaves.length;
    let lo = 0;
    let hi = this.cumArea.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (this.cumArea[mid] <= target) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }
}

function polar(rnd: () => number, maxR: number): [number, number] {
  const r = Math.sqrt(rnd()) * maxR;
  const a = rnd() * Math.PI * 2;
  return [r * Math.cos(a), r * Math.sin(a)];
}
