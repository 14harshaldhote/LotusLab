import { interpolateRgb } from "d3";

/** Sky appearance as a pure function of sun elevation and cloud cover. */

const STOPS: Array<[number, string, string]> = [
  // elevation deg, zenith colour, horizon colour
  [-18, "#04060f", "#0a0f24"],
  [-8, "#0d1636", "#2a2c55"],
  [-3, "#1f2b5a", "#b4605a"],
  [0, "#30457f", "#ef8f5c"],
  [4, "#3f63a5", "#f6bd7b"],
  [10, "#4a86c5", "#b6dbf0"],
  [35, "#2c73c2", "#a5d4f3"],
  [90, "#2468b8", "#9dcff0"],
];

export interface Sky {
  zenith: string;
  horizon: string;
  ambient: number; // 0 (dark) .. 1 (full daylight)
  starOpacity: number;
  sunColor: string;
}

export function skyAt(elevationDeg: number, cloudPct: number): Sky {
  const e = Math.min(Math.max(elevationDeg, STOPS[0][0]), STOPS[STOPS.length - 1][0]);
  let k = 0;
  while (k < STOPS.length - 2 && e > STOPS[k + 1][0]) k++;
  const [e0, z0, h0] = STOPS[k];
  const [e1, z1, h1] = STOPS[k + 1];
  const f = (e - e0) / (e1 - e0);
  const cloud = Math.min(Math.max(cloudPct / 100, 0), 1);
  let zenith = interpolateRgb(z0, z1)(f);
  let horizon = interpolateRgb(h0, h1)(f);
  // overcast skies wash colour towards a grey of similar brightness
  const day = clamp01((elevationDeg + 6) / 16);
  const grey = interpolateRgb("#1b1f2a", "#9aa3ad")(day);
  zenith = interpolateRgb(zenith, grey)(cloud * 0.65);
  horizon = interpolateRgb(horizon, grey)(cloud * 0.55);
  const ambient = Math.max(0.12, clamp01((elevationDeg + 8) / 22)) * (1 - 0.45 * cloud);
  const starOpacity = clamp01((-elevationDeg - 4) / 8) * (1 - cloud);
  const sunColor = interpolateRgb("#ff7b39", "#fff6d8")(clamp01(elevationDeg / 15));
  return { zenith, horizon, ambient, starOpacity, sunColor };
}

export function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}
