import * as d3 from "d3";
import { useEffect, useMemo, useRef } from "react";

import { LeafLayout, mulberry32 } from "../engine/layout";
import { clamp01, skyAt } from "../engine/sky";
import type { Sample } from "../engine/timeline";

/**
 * The living pond. The SVG skeleton is built once; every frame only updates attributes
 * from the current interpolated sample, so scrubbing is a handful of DOM writes.
 */

const W = 960;
const H = 420;
const HORIZON = 238;
const POND = { cx: 480, cy: 332, rx: 410, ry: 74 };
const STAR_COUNT = 90;
const RAIN_COUNT = 140;
const LAND_PATH = `M0,${HORIZON} C120,${HORIZON - 40} 240,${HORIZON - 10} 360,${HORIZON - 30} S620,${HORIZON - 55} 760,${HORIZON - 20} S900,${HORIZON - 30} ${W},${HORIZON - 12} L${W},${H} L0,${H} Z`;
const CLOUDS = [
  { x: 80, y: 60, s: 1.1 },
  { x: 300, y: 95, s: 0.8 },
  { x: 520, y: 50, s: 1.3 },
  { x: 720, y: 110, s: 0.9 },
  { x: 900, y: 70, s: 1.0 },
  { x: 1100, y: 40, s: 1.2 },
];

interface FlowerDatum {
  x: number;
  y: number;
  index: number; // position of the parent leaf in the growth order
}

interface Props {
  sample: Sample;
  latitude: number;
  surfaceAreaFull: number;
  localHour: number;
  label?: string;
}

interface Refs {
  skyTop: d3.Selection<SVGStopElement, unknown, null, undefined>;
  skyBottom: d3.Selection<SVGStopElement, unknown, null, undefined>;
  stars: d3.Selection<SVGGElement, unknown, null, undefined>;
  sun: d3.Selection<SVGGElement, unknown, null, undefined>;
  sunDisk: d3.Selection<SVGCircleElement, unknown, null, undefined>;
  moon: d3.Selection<SVGGElement, unknown, null, undefined>;
  clouds: d3.Selection<SVGGElement, unknown, null, undefined>;
  cloudShapes: d3.Selection<SVGGElement, (typeof CLOUDS)[number], SVGGElement, unknown>;
  land: d3.Selection<SVGGElement, unknown, null, undefined>;
  water: d3.Selection<SVGEllipseElement, unknown, null, undefined>;
  waterFar: d3.Selection<SVGStopElement, unknown, null, undefined>;
  waterNear: d3.Selection<SVGStopElement, unknown, null, undefined>;
  lotus: d3.Selection<SVGGElement, unknown, null, undefined>;
  leaves: d3.Selection<SVGPathElement, unknown, SVGGElement, unknown>;
  flowers: d3.Selection<SVGGElement, FlowerDatum, SVGGElement, unknown>;
  rain: d3.Selection<SVGLineElement, number, SVGGElement, unknown>;
  ripples: d3.Selection<SVGGElement, unknown, null, undefined>;
  night: d3.Selection<SVGRectElement, unknown, null, undefined>;
  spill: d3.Selection<SVGGElement, unknown, null, undefined>;
  mud: d3.Selection<SVGEllipseElement, unknown, null, undefined>;
}

export function PondScene({ sample, latitude, surfaceAreaFull, localHour, label }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const refs = useRef<Refs | null>(null);
  const layout = useMemo(() => new LeafLayout(), []);
  const uid = useMemo(() => `p${Math.random().toString(36).slice(2, 8)}`, []);

  useEffect(() => {
    refs.current = build(svgRef.current!, layout, uid);
  }, [layout, uid]);

  useEffect(() => {
    if (refs.current) update(refs.current, sample, latitude, surfaceAreaFull, localHour, layout);
  }, [sample, latitude, surfaceAreaFull, localHour, layout]);

  return (
    <svg
      ref={svgRef}
      className="pond-scene"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={label ?? "Simulated pond at the selected time"}
    />
  );
}

function build(svgEl: SVGSVGElement, layout: LeafLayout, uid: string): Refs {
  const svg = d3.select(svgEl);
  svg.selectAll("*").remove();
  const defs = svg.append("defs");

  const sky = defs.append("linearGradient").attr("id", `${uid}-sky`).attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", 1);
  const skyTop = sky.append("stop").attr("offset", "0%");
  const skyBottom = sky.append("stop").attr("offset", "100%");

  const glow = defs.append("radialGradient").attr("id", `${uid}-glow`);
  glow.append("stop").attr("offset", "0%").attr("stop-color", "#fff6d8").attr("stop-opacity", 0.9);
  glow.append("stop").attr("offset", "100%").attr("stop-color", "#fff6d8").attr("stop-opacity", 0);

  // water reflects the sky: stop colours are updated every frame
  const waterGrad = defs.append("linearGradient").attr("id", `${uid}-water`).attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", 1);
  const waterFar = waterGrad.append("stop").attr("offset", "0%");
  const waterNear = waterGrad.append("stop").attr("offset", "100%");

  defs.append("clipPath").attr("id", `${uid}-land`).append("path").attr("d", LAND_PATH);

  const pondClip = defs.append("clipPath").attr("id", `${uid}-pond`);
  pondClip.append("ellipse").attr("cx", POND.cx).attr("cy", POND.cy).attr("rx", POND.rx).attr("ry", POND.ry);

  svg.append("rect").attr("width", W).attr("height", HORIZON + 4).attr("fill", `url(#${uid}-sky)`);

  const rnd = mulberry32(7);
  const stars = svg.append("g").attr("class", "stars");
  for (let i = 0; i < STAR_COUNT; i++) {
    stars
      .append("circle")
      .attr("cx", rnd() * W)
      .attr("cy", rnd() * (HORIZON - 30))
      .attr("r", 0.4 + rnd() * 1.1)
      .attr("fill", "#fff")
      .attr("opacity", 0.4 + rnd() * 0.6);
  }

  const moon = svg.append("g");
  moon.append("circle").attr("r", 14).attr("fill", "#e9eef7");
  moon.append("circle").attr("r", 14).attr("cx", 6).attr("cy", -3).attr("fill", "#0d1636").attr("opacity", 0.85);

  const sun = svg.append("g");
  sun.append("circle").attr("r", 60).attr("fill", `url(#${uid}-glow)`);
  const sunDisk = sun.append("circle").attr("r", 17);

  const clouds = svg.append("g");
  const cloudShapes = clouds
    .selectAll<SVGGElement, (typeof CLOUDS)[number]>("g")
    .data(CLOUDS)
    .join("g");
  cloudShapes.each(function (c) {
    const g = d3.select(this);
    for (const [dx, dy, r] of [
      [0, 0, 26],
      [28, -10, 30],
      [58, 0, 24],
      [30, 8, 26],
    ])
      g.append("circle").attr("cx", dx * c.s).attr("cy", dy * c.s).attr("r", r * c.s);
  });

  const land = svg.append("g");
  land
    .append("path")
    .attr("d", LAND_PATH)
    .attr("fill", "#2f5d3a");
  land.append("rect").attr("y", HORIZON).attr("width", W).attr("height", H - HORIZON).attr("fill", "#4f7f45");
  // reeds along the bank
  const reeds = land.append("g").attr("stroke", "#2c4d2a").attr("stroke-width", 2).attr("stroke-linecap", "round");
  for (let i = 0; i < 40; i++) {
    const a = Math.PI * (0.05 + 0.9 * rnd()) + (rnd() < 0.5 ? 0 : Math.PI);
    const x = POND.cx + Math.cos(a) * (POND.rx + 8);
    const y = POND.cy + Math.sin(a) * (POND.ry + 6);
    reeds.append("path").attr("d", `M${x},${y} q${(rnd() - 0.5) * 8},-14 ${(rnd() - 0.5) * 6},-${20 + rnd() * 20}`).attr("fill", "none");
  }

  // dry basin, then the water surface scaled by the modelled area
  const mud = svg.append("ellipse").attr("cx", POND.cx).attr("cy", POND.cy).attr("rx", POND.rx).attr("ry", POND.ry).attr("fill", "#7a5a3a");
  const water = svg.append("ellipse").attr("cx", POND.cx).attr("cy", POND.cy).attr("fill", `url(#${uid}-water)`);

  const ripples = svg.append("g").attr("clip-path", `url(#${uid}-pond)`);
  for (let i = 0; i < 18; i++) {
    ripples
      .append("ellipse")
      .attr("class", "ripple")
      .attr("cx", POND.cx + (rnd() - 0.5) * POND.rx * 1.6)
      .attr("cy", POND.cy + (rnd() - 0.5) * POND.ry * 1.4)
      .attr("rx", 10)
      .attr("ry", 3)
      .style("animation-delay", `${(rnd() * 1.6).toFixed(2)}s`);
  }

  // leaves live in unit-disk coordinates; the group transform maps them onto the water
  const lotus = svg.append("g");
  const leaves = lotus
    .selectAll<SVGPathElement, unknown>("path")
    .data(layout.leaves)
    .join("path")
    .attr("d", (l) => leafPath(l.x, l.y, l.r, l.rot))
    .attr("fill", (_, i) => d3.interpolateRgb("#3f8f4f", "#2e7542")((i % 7) / 6))
    .attr("stroke", "#24563a")
    .attr("stroke-width", 1)
    .attr("vector-effect", "non-scaling-stroke") as unknown as d3.Selection<SVGPathElement, unknown, SVGGElement, unknown>;
  const flowerData: FlowerDatum[] = layout.leaves.flatMap((l, index) => (l.flower ? [{ x: l.x, y: l.y, index }] : []));
  const flowers = lotus
    .selectAll<SVGGElement, FlowerDatum>("g")
    .data(flowerData)
    .join("g")
    .attr("transform", (f) => `translate(${f.x},${f.y})`) as unknown as d3.Selection<SVGGElement, FlowerDatum, SVGGElement, unknown>;
  flowers.append("circle").attr("r", 0.022).attr("fill", "#f3a6c3");
  flowers.append("circle").attr("r", 0.009).attr("fill", "#ffe08a");

  const spill = svg.append("g").attr("opacity", 0);
  spill
    .append("path")
    .attr("d", `M${POND.cx + POND.rx - 20},${POND.cy - 6} q40,10 60,60 l-14,4 q-18,-44 -50,-52 Z`)
    .attr("fill", "#5aa7c7")
    .attr("class", "spill");

  const rainG = svg.append("g").attr("class", "rain");
  const rain = rainG
    .selectAll<SVGLineElement, number>("line")
    .data(d3.range(RAIN_COUNT))
    .join("line")
    .attr("x1", () => rnd() * W)
    .attr("y1", () => rnd() * H - H)
    .attr("x2", function () {
      return Number(d3.select(this).attr("x1")) - 4;
    })
    .attr("y2", function () {
      return Number(d3.select(this).attr("y1")) + 14;
    })
    .style("animation-delay", () => `${(rnd() * 0.9).toFixed(2)}s`);

  // darkens the land and pond only; the sky gets its own colours from skyAt()
  const night = svg
    .append("rect")
    .attr("width", W)
    .attr("height", H)
    .attr("clip-path", `url(#${uid}-land)`)
    .attr("fill", "#050a1a")
    .attr("pointer-events", "none")
    .style("mix-blend-mode", "multiply");

  return { skyTop, skyBottom, stars, sun, sunDisk, moon, clouds, cloudShapes, land, water, waterFar, waterNear, lotus, leaves, flowers, rain, ripples, night, spill, mud };
}

function leafPath(x: number, y: number, r: number, rotDeg: number): string {
  // a round pad with a narrow notch to the centre
  const a = (rotDeg * Math.PI) / 180;
  const n = 0.22;
  const x1 = x + r * Math.cos(a - n);
  const y1 = y + r * Math.sin(a - n);
  const x2 = x + r * Math.cos(a + n);
  const y2 = y + r * Math.sin(a + n);
  return `M${x},${y}L${x1},${y1}A${r},${r} 0 1 0 ${x2},${y2}Z`;
}

function sunXY(azimuthDeg: number, elevationDeg: number, latitude: number): [number, number] {
  // Viewer faces the equator: south in the north hemisphere, north in the south.
  const centre = latitude >= 0 ? 180 : 0;
  const dx = ((((azimuthDeg - centre + 540) % 360) + 360) % 360) - 180;
  const x = W / 2 + (dx / 120) * (W / 2);
  const y = HORIZON - Math.sin((Math.max(elevationDeg, -20) * Math.PI) / 180) * (HORIZON - 30);
  return [x, y];
}

function update(r: Refs, s: Sample, latitude: number, aFull: number, localHour: number, layout: LeafLayout) {
  const elev = s.sun_elevation_deg;
  const cloud = s.cloud_cover_pct;
  const sky = skyAt(elev, cloud);
  r.skyTop.attr("stop-color", sky.zenith);
  r.skyBottom.attr("stop-color", sky.horizon);
  r.stars.attr("opacity", sky.starOpacity);

  const [sx, sy] = sunXY(s.sun_azimuth_deg, elev, latitude);
  r.sun.attr("transform", `translate(${sx},${sy})`).attr("opacity", elev > -2 ? 1 - 0.7 * (cloud / 100) : 0);
  r.sunDisk.attr("fill", sky.sunColor);
  const [mx, my] = sunXY(s.sun_azimuth_deg + 180, -elev * 0.8, latitude);
  r.moon.attr("transform", `translate(${mx},${my})`).attr("opacity", elev < -4 ? 0.9 * (1 - cloud / 140) : 0);

  // clouds drift with the wind, positioned from simulation time (deterministic)
  const drift = (s.time / 60) * Math.max(s.wind_speed_ms, 0.5) * 0.4;
  const cloudFill = d3.interpolateRgb("#2a3045", "#f4f6fa")(sky.ambient);
  r.clouds.attr("opacity", clamp01(cloud / 100) * 0.95).attr("fill", cloudFill);
  r.cloudShapes.attr("transform", (c) => `translate(${((((c.x + drift) % 1260) + 1260) % 1260) - 150},${c.y})`);

  // water: area scales with depth, radius with sqrt(area)
  const k = Math.sqrt(clamp01(s.surface_area_m2 / aFull));
  const rx = POND.rx * k;
  const ry = POND.ry * k;
  r.water.attr("rx", rx).attr("ry", ry);
  r.waterFar.attr("stop-color", d3.interpolateRgb(sky.horizon, "#1f6f93")(0.55));
  r.waterNear.attr("stop-color", d3.interpolateRgb(sky.zenith, "#0f3f57")(0.6));
  r.mud.attr("fill", s.depth_m < 0.15 ? "#8a6a44" : "#6d5034");

  // lotus: show the first N leaves of the fixed layout
  r.lotus.attr("transform", `translate(${POND.cx},${POND.cy}) scale(${rx},${ry})`);
  const visible = layout.countFor(s.cover_of_water);
  r.leaves.attr("display", (_, i) => (i < visible ? null : "none"));
  const bloom = s.phase >= 2 && localHour > 5.5 && localHour < 15 && s.saturation > 0.2 ? 1 : 0;
  r.flowers.attr("display", (f) => (bloom && f.index < visible ? null : "none"));

  // rain intensity -> visible drops and ripples
  const intensity = clamp01(s.precipitation_mm / 6);
  const drops = Math.round(intensity * RAIN_COUNT);
  r.rain.attr("display", (d) => (d < drops ? null : "none"));
  r.ripples.attr("opacity", intensity > 0.02 ? 0.3 + 0.7 * intensity : 0);
  r.spill.attr("opacity", s.overflow_m3 > 0.001 ? 1 : 0);
  r.night.attr("opacity", 1 - sky.ambient);
}
