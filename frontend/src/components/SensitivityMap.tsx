import * as d3 from "d3";

import type { SensitivityResponse } from "../api/types";

interface Props {
  data: SensitivityResponse;
  onPick: (temperatureOffset: number, rainMultiplier: number) => void;
}

/** Heatmap of final lotus cover over temperature offset × rain multiplier. */
export function SensitivityMap({ data, onPick }: Props) {
  const temps = data.temperature_offsets_c;
  const rains = data.precipitation_multipliers;
  const cell = 46;
  const left = 64;
  const top = 26;
  const w = left + rains.length * cell + 10;
  const h = top + temps.length * cell + 36;
  const values = data.final_cover_fraction;
  const color = d3.scaleSequential(d3.interpolateYlGn).domain([0, Math.max(0.05, d3.max(values.flat()) ?? 1)]);
  return (
    <div className="sensitivity">
      <h3>Final lotus cover (% of the brim-full pond)</h3>
      <p className="fine">
        Each cell is a full re-run of the simulation on the same weather ({temps.length * rains.length} runs in {data.compute_ms.toFixed(0)} ms). Click a
        cell to load it as the what-if scenario.
      </p>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Sensitivity heatmap">
        {rains.map((r, j) => (
          <text key={`r${j}`} x={left + j * cell + cell / 2} y={top - 8} textAnchor="middle" className="tick">
            {r}×
          </text>
        ))}
        {temps.map((t, i) => (
          <text key={`t${i}`} x={left - 8} y={top + i * cell + cell / 2 + 4} textAnchor="end" className="tick">
            {t > 0 ? "+" : ""}
            {t} °C
          </text>
        ))}
        {temps.map((t, i) =>
          rains.map((r, j) => {
            const v = values[i][j];
            return (
              <g key={`${i}-${j}`} className="cell" onClick={() => onPick(t, r)}>
                <rect x={left + j * cell} y={top + i * cell} width={cell - 2} height={cell - 2} fill={color(v)} rx={4} />
                <text x={left + j * cell + cell / 2 - 1} y={top + i * cell + cell / 2 + 4} textAnchor="middle" className={v > 0.6 * color.domain()[1] ? "light" : ""}>
                  {Math.round(v * 100)}
                </text>
                <title>
                  {`${t} °C, ${r}× rain: cover ${(v * 100).toFixed(1)}%, saturation ${(data.final_saturation[i][j] * 100).toFixed(1)}%, final depth ${data.final_depth_m[i][j].toFixed(2)} m, overflow ${data.overflow_m3[i][j].toFixed(1)} m³`}
                </title>
              </g>
            );
          }),
        )}
        <text x={left + (rains.length * cell) / 2} y={h - 8} textAnchor="middle" className="axis-label">
          rain multiplier →
        </text>
      </svg>
    </div>
  );
}
