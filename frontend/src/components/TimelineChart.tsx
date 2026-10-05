import * as d3 from "d3";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Milestones } from "../api/types";
import type { Timeline } from "../engine/timeline";

/**
 * Depth, lotus saturation and rain on one shared time axis.
 *
 * Paths are rebuilt only when the timeline (or the size) changes. Scrubbing moves a
 * single cursor group, so the chart costs a couple of attribute writes per frame.
 * Click or drag anywhere on the chart to seek.
 */

interface Props {
  timeline: Timeline;
  variant?: Timeline | null;
  milestones: Milestones;
  time: number;
  utcOffsetS: number;
  maxDepth: number;
  onSeek: (t: number) => void;
}

const M = { top: 18, right: 52, bottom: 26, left: 46 };
const HEIGHT = 230;
const RAIN_BAND = 42;

export function TimelineChart({ timeline, variant, milestones, time, utcOffsetS, maxDepth, onSeek }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const cursorRef = useRef<SVGGElement | null>(null);
  const scalesRef = useRef<{ yDepth: d3.ScaleLinear<number, number>; ySat: d3.ScaleLinear<number, number> } | null>(null);
  const [width, setWidth] = useState(800);

  useEffect(() => {
    const el = wrapRef.current!;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(320, Math.floor(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const x = useMemo(
    () => d3.scaleUtc().domain([new Date((timeline.t0 + utcOffsetS) * 1000), new Date((timeline.tEnd + utcOffsetS) * 1000)]).range([M.left, width - M.right]),
    [timeline, utcOffsetS, width],
  );

  // full redraw when data or size changes
  useEffect(() => {
    const svg = d3.select(svgRef.current!);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${HEIGHT}`);
    const plotBottom = HEIGHT - M.bottom - RAIN_BAND;
    const yDepth = d3.scaleLinear().domain([0, maxDepth * 1.05]).range([plotBottom, M.top]);
    const ySat = d3.scaleLinear().domain([0, 1]).range([plotBottom, M.top]);
    const n = timeline.n;
    const xs = new Float64Array(n);
    for (let i = 0; i < n; i++) xs[i] = x(new Date((timeline.t0 + i * timeline.dt + utcOffsetS) * 1000));

    // night shading from day phase
    const nights = svg.append("g").attr("class", "night-bands");
    const elev = timeline.columns.sun_elevation_deg;
    let start = -1;
    for (let i = 0; i <= n; i++) {
      const dark = i < n && elev[i] < -0.833;
      if (dark && start < 0) start = i;
      if (!dark && start >= 0) {
        nights.append("rect").attr("x", xs[start]).attr("width", xs[Math.min(i, n - 1)] - xs[start]).attr("y", M.top).attr("height", HEIGHT - M.bottom - M.top);
        start = -1;
      }
    }

    const line = (tl: Timeline, col: string, y: d3.ScaleLinear<number, number>) => {
      const v = tl.columns[col];
      return d3.line<number>().x((i) => xs[i]).y((i) => y(v[i]))(d3.range(tl.n)) ?? "";
    };

    // rain bars in their own band
    const rainMax = Math.max(2, d3.max(timeline.columns.precipitation_mm) ?? 0);
    const yRain = d3.scaleLinear().domain([0, rainMax]).range([HEIGHT - M.bottom, HEIGHT - M.bottom - RAIN_BAND + 6]);
    const bw = Math.max(1, (width - M.left - M.right) / n);
    svg
      .append("g")
      .attr("class", "rain-bars")
      .selectAll("rect")
      .data(d3.range(n).filter((i) => timeline.columns.precipitation_mm[i] > 0.05))
      .join("rect")
      .attr("x", (i) => xs[i] - bw)
      .attr("width", bw)
      .attr("y", (i) => yRain(timeline.columns.precipitation_mm[i]))
      .attr("height", (i) => HEIGHT - M.bottom - yRain(timeline.columns.precipitation_mm[i]));

    const depthArea = d3
      .area<number>()
      .x((i) => xs[i])
      .y0(plotBottom)
      .y1((i) => yDepth(timeline.columns.depth_m[i]));
    svg.append("path").attr("class", "depth-area").attr("d", depthArea(d3.range(n)) ?? "");
    svg.append("path").attr("class", "line depth").attr("d", line(timeline, "depth_m", yDepth));
    svg.append("path").attr("class", "line saturation").attr("d", line(timeline, "saturation", ySat));
    if (variant && variant.n === n) {
      svg.append("path").attr("class", "line depth variant").attr("d", line(variant, "depth_m", yDepth));
      svg.append("path").attr("class", "line saturation variant").attr("d", line(variant, "saturation", ySat));
    }

    // spill level
    svg
      .append("line")
      .attr("class", "spill-level")
      .attr("x1", M.left)
      .attr("x2", width - M.right)
      .attr("y1", yDepth(maxDepth))
      .attr("y2", yDepth(maxDepth));

    // the puzzle in real life: half full vs full
    const marks: Array<[number | null, string]> = [
      [milestones.cover_50, "half full"],
      [milestones.cover_full, "full"],
    ];
    const mg = svg.append("g").attr("class", "milestones");
    for (const [t, label] of marks) {
      if (t == null) continue;
      const mx = x(new Date((t + utcOffsetS) * 1000));
      mg.append("line").attr("x1", mx).attr("x2", mx).attr("y1", M.top).attr("y2", plotBottom);
      mg.append("text").attr("x", mx + 4).attr("y", M.top + 10).text(label);
    }

    svg
      .append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${HEIGHT - M.bottom})`)
      .call(d3.axisBottom(x).ticks(Math.max(3, Math.floor(width / 110))).tickSizeOuter(0));
    svg
      .append("g")
      .attr("class", "axis depth")
      .attr("transform", `translate(${M.left},0)`)
      .call(d3.axisLeft(yDepth).ticks(4).tickFormat((d) => `${d} m`));
    svg
      .append("g")
      .attr("class", "axis saturation")
      .attr("transform", `translate(${width - M.right},0)`)
      .call(d3.axisRight(ySat).ticks(4).tickFormat(d3.format(".0%")));

    const cursor = svg.append("g").attr("class", "cursor");
    cursor.append("line").attr("y1", M.top - 6).attr("y2", HEIGHT - M.bottom);
    cursor.append("circle").attr("class", "dot depth").attr("r", 4);
    cursor.append("circle").attr("class", "dot saturation").attr("r", 4);
    cursorRef.current = cursor.node();
    scalesRef.current = { yDepth, ySat };

    // seeking by pointer
    const toTime = (px: number) => x.invert(px).getTime() / 1000 - utcOffsetS;
    const overlay = svg
      .append("rect")
      .attr("class", "overlay")
      .attr("x", M.left)
      .attr("y", 0)
      .attr("width", width - M.left - M.right)
      .attr("height", HEIGHT);
    overlay.on("pointerdown", (ev: PointerEvent) => {
      (ev.target as Element).setPointerCapture(ev.pointerId);
      onSeek(toTime(d3.pointer(ev)[0]));
    });
    overlay.on("pointermove", (ev: PointerEvent) => {
      if (ev.buttons & 1) onSeek(toTime(d3.pointer(ev)[0]));
    });
  }, [timeline, variant, milestones, width, x, utcOffsetS, maxDepth, onSeek]);

  // cheap per-frame cursor update
  useEffect(() => {
    const node = cursorRef.current;
    const scales = scalesRef.current;
    if (!node || !scales) return;
    const { yDepth, ySat } = scales;
    const cx = x(new Date((timeline.clamp(time) + utcOffsetS) * 1000));
    const g = d3.select(node).attr("transform", `translate(${cx},0)`);
    g.select(".dot.depth").attr("cy", yDepth(timeline.value("depth_m", time)));
    g.select(".dot.saturation").attr("cy", ySat(timeline.value("saturation", time)));
  });

  return (
    <div className="chart" ref={wrapRef}>
      <svg ref={svgRef} role="img" aria-label="Pond depth, lotus saturation and rainfall over time" />
      <div className="legend">
        <span className="key depth">water depth</span>
        <span className="key saturation">lotus saturation</span>
        <span className="key rain">rain</span>
        {variant && <span className="key variant">what-if (dashed)</span>}
        <span className="key night">night</span>
      </div>
    </div>
  );
}
