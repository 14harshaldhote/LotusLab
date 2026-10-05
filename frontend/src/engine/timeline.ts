import type { TimelinePayload } from "../api/types";

/**
 * Columnar view over a backend timeline.
 *
 * The backend is the source of truth: this class never simulates anything, it only
 * looks up and linearly interpolates between backend rows. Every lookup is O(1):
 * one subtraction and division to find the row, one lerp per requested column.
 */

export const PHASE = { NIGHT: 0, TWILIGHT: 1, GOLDEN: 2, DAY: 3 } as const;

export type Sample = Record<string, number> & { time: number; phase: number };

export interface SolarEvent {
  time: number;
  kind: "sunrise" | "sunset";
}

export class Timeline {
  readonly t0: number;
  readonly dt: number;
  readonly n: number;
  readonly columns: Record<string, Float64Array>;
  readonly names: string[];
  readonly events: SolarEvent[];
  readonly rainStarts: number[];

  constructor(payload: TimelinePayload) {
    if (payload.n < 2) throw new Error("timeline needs at least two rows");
    this.t0 = payload.t0;
    this.dt = payload.dt;
    this.n = payload.n;
    this.columns = {};
    for (const [name, values] of Object.entries(payload.columns)) {
      if (values.length !== payload.n) throw new Error(`column ${name} has ${values.length} rows, expected ${payload.n}`);
      this.columns[name] = Float64Array.from(values);
    }
    this.names = Object.keys(this.columns);
    this.events = findSolarEvents(this);
    this.rainStarts = findRainStarts(this);
  }

  get tEnd(): number {
    return this.t0 + (this.n - 1) * this.dt;
  }

  clamp(t: number): number {
    return Math.min(Math.max(t, this.t0), this.tEnd);
  }

  /** Row index and fraction towards the next row. O(1). */
  locate(t: number): [number, number] {
    const x = (t - this.t0) / this.dt;
    if (!(x > 0)) return [0, 0];
    if (x >= this.n - 1) return [this.n - 1, 0];
    const i = Math.floor(x);
    return [i, x - i];
  }

  /** One interpolated column value at time t. O(1). */
  value(name: string, t: number): number {
    const col = this.columns[name];
    if (!col) throw new Error(`unknown column ${name}`);
    const [i, f] = this.locate(t);
    return f === 0 ? col[i] : col[i] + (col[i + 1] - col[i]) * f;
  }

  /** Every column at time t. O(columns). */
  sample(t: number): Sample {
    const [i, f] = this.locate(t);
    const out = { time: t } as Sample;
    for (const name of this.names) {
      const col = this.columns[name];
      out[name] = f === 0 ? col[i] : col[i] + (col[i + 1] - col[i]) * f;
    }
    out.phase = phaseOf(out.sun_elevation_deg);
    return out;
  }

  /** Total of a flux between two instants using backend prefix sums. O(1). */
  between(flux: string, ta: number, tb: number): number {
    const name = `cum_${flux}`;
    return this.value(name, Math.max(ta, tb)) - this.value(name, Math.min(ta, tb));
  }

  /** First solar event of the given kind strictly after t. O(log events). */
  nextEvent(t: number, kind: SolarEvent["kind"]): number | null {
    const list = this.events;
    let lo = 0;
    let hi = list.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (list[mid].time <= t) lo = mid + 1;
      else hi = mid;
    }
    for (let k = lo; k < list.length; k++) if (list[k].kind === kind) return list[k].time;
    return null;
  }

  nextRain(t: number): number | null {
    for (const s of this.rainStarts) if (s > t + 1) return s;
    return null;
  }
}

export function phaseOf(elevationDeg: number): number {
  if (elevationDeg < -6) return PHASE.NIGHT;
  if (elevationDeg < 0) return PHASE.TWILIGHT;
  if (elevationDeg < 6) return PHASE.GOLDEN;
  return PHASE.DAY;
}

/** Human label that distinguishes dawn from dusk using the sun's trend. */
export function phaseLabel(phase: number, rising: boolean): string {
  switch (phase) {
    case PHASE.NIGHT:
      return "Night";
    case PHASE.TWILIGHT:
      return rising ? "Dawn" : "Dusk";
    case PHASE.GOLDEN:
      return rising ? "Sunrise glow" : "Evening golden hour";
    default:
      return rising ? "Morning" : "Afternoon";
  }
}

/** Sunrise / sunset: interpolated zero crossings of the -0.833 deg horizon. */
function findSolarEvents(tl: Timeline): SolarEvent[] {
  const e = tl.columns.sun_elevation_deg;
  if (!e) return [];
  const h = -0.833;
  const events: SolarEvent[] = [];
  for (let i = 0; i + 1 < tl.n; i++) {
    const a = e[i] - h;
    const b = e[i + 1] - h;
    if ((a < 0 && b >= 0) || (a >= 0 && b < 0)) {
      const f = a / (a - b);
      events.push({ time: tl.t0 + (i + f) * tl.dt, kind: a < 0 ? "sunrise" : "sunset" });
    }
  }
  return events;
}

function findRainStarts(tl: Timeline): number[] {
  const p = tl.columns.precipitation_mm;
  if (!p) return [];
  const starts: number[] = [];
  for (let i = 1; i < tl.n; i++) if (p[i] >= 0.2 && p[i - 1] < 0.2) starts.push(tl.t0 + (i - 1) * tl.dt);
  return starts;
}

/** Wall-clock formatting in the location's own time zone. */
export function localParts(t: number, utcOffsetS: number) {
  const d = new Date((t + utcOffsetS) * 1000);
  return {
    date: d.toISOString().slice(0, 10),
    time: d.toISOString().slice(11, 16),
    weekday: d.toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" }),
    hour: d.getUTCHours() + d.getUTCMinutes() / 60,
  };
}
