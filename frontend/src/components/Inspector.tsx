import type { Provenance, Summary } from "../api/types";
import type { Timing } from "../api/client";
import { localParts, phaseLabel, type Sample, type Timeline } from "../engine/timeline";

interface Props {
  sample: Sample;
  timeline: Timeline;
  summary: Summary;
  provenance: Provenance;
  timing: Timing | null;
  seekMicros: number;
}

const f1 = (v: number) => v.toFixed(1);
const f2 = (v: number) => v.toFixed(2);
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

export function Inspector({ sample: s, timeline, summary, provenance, timing, seekMicros }: Props) {
  const rising = timeline.value("sun_elevation_deg", s.time + 600) > s.sun_elevation_deg;
  const since = (flux: string) => timeline.between(flux, timeline.t0, s.time);
  const ledger: Array<[string, number, number]> = [
    ["Rain on pond", since("rain_m3"), 1],
    ["Catchment runoff", since("runoff_m3"), 1],
    ["Evaporation", since("evaporation_m3"), -1],
    ["Seepage", since("seepage_m3"), -1],
    ["Overflow", since("overflow_m3"), -1],
  ];
  const net = ledger.reduce((acc, [, v, sign]) => acc + sign * v, 0);
  const halfToFull =
    summary.milestones.cover_50 != null && summary.milestones.cover_full != null
      ? (summary.milestones.cover_full - summary.milestones.cover_50) / 3600
      : null;
  const fmtTime = (t: number | null) => {
    if (t == null) return "not reached";
    const p = localParts(t, provenance.utc_offset_s);
    return `${p.date} ${p.time}`;
  };

  return (
    <aside className="inspector">
      <section>
        <h3>{phaseLabel(s.phase, rising)}</h3>
        <dl>
          <dt>Sun elevation</dt>
          <dd>{f1(s.sun_elevation_deg)}°</dd>
          <dt>Air temperature</dt>
          <dd>{f1(s.temperature_c)} °C</dd>
          <dt>Cloud cover</dt>
          <dd>{s.cloud_cover_pct.toFixed(0)}%</dd>
          <dt>Sunlight</dt>
          <dd>{s.shortwave_wm2.toFixed(0)} W/m²</dd>
          <dt>Rain this hour</dt>
          <dd>{f2(s.precipitation_mm)} mm</dd>
          <dt>Wind</dt>
          <dd>{f1(s.wind_speed_ms)} m/s</dd>
        </dl>
      </section>

      <section>
        <h3>Pond (modelled)</h3>
        <dl>
          <dt>Water depth</dt>
          <dd>{f2(s.depth_m)} m</dd>
          <dt>Volume</dt>
          <dd>
            {f1(s.volume_m3)} m³ ({pct(s.fill_fraction)} of brim)
          </dd>
          <dt>Water surface</dt>
          <dd>{f1(s.surface_area_m2)} m²</dd>
          <dt>Catchment soil</dt>
          <dd>{f1(s.soil_mm)} mm stored</dd>
        </dl>
      </section>

      <section>
        <h3>Lotus (modelled)</h3>
        <dl>
          <dt>Leaf cover</dt>
          <dd>
            {f1(s.cover_m2)} m² ({pct(s.cover_of_water)} of water)
          </dd>
          <dt>Pond saturation</dt>
          <dd>{pct(s.saturation)}</dd>
          <dt>Net growth rate</dt>
          <dd>{(s.growth_rate_per_day * 100).toFixed(1)}% / day</dd>
          <dt>Limits: temp · light · depth</dt>
          <dd>
            {f2(s.f_temperature)} · {f2(s.f_light)} · {f2(s.f_depth)}
          </dd>
          <dt>Half full</dt>
          <dd>{fmtTime(summary.milestones.cover_50)}</dd>
          <dt>Full</dt>
          <dd>{fmtTime(summary.milestones.cover_full)}</dd>
          {halfToFull != null && (
            <>
              <dt>Half → full</dt>
              <dd>{halfToFull.toFixed(0)} h</dd>
            </>
          )}
        </dl>
      </section>

      <section>
        <h3>Water ledger since start</h3>
        <table className="ledger">
          <tbody>
            {ledger.map(([name, v, sign]) => (
              <tr key={name}>
                <td>{name}</td>
                <td className={sign > 0 ? "in" : "out"}>
                  {sign > 0 ? "+" : "−"}
                  {f2(v)} m³
                </td>
              </tr>
            ))}
            <tr className="total">
              <td>Net change</td>
              <td>
                {net >= 0 ? "+" : "−"}
                {f2(Math.abs(net))} m³
              </td>
            </tr>
          </tbody>
        </table>
        <p className="fine">Mass balance error over the run: {summary.mass_balance_error_m3.toExponential(1)} m³</p>
      </section>

      <section className="provenance">
        <h3>Data and performance</h3>
        <dl>
          <dt>Weather source</dt>
          <dd className={provenance.source === "synthetic" ? "warn" : ""}>
            {provenance.source === "synthetic" ? "Synthetic demo weather (not real)" : provenance.source.replace("open-meteo-", "Open-Meteo ")}
            {provenance.stale && " · stale cached copy"}
          </dd>
          <dt>Fetched</dt>
          <dd>{new Date(provenance.fetched_at * 1000).toLocaleString()}</dd>
          <dt>Time zone</dt>
          <dd>{provenance.timezone}</dd>
          {Object.keys(provenance.gaps_filled).length > 0 && (
            <>
              <dt>Gaps filled</dt>
              <dd>
                {Object.entries(provenance.gaps_filled)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(", ")}
              </dd>
            </>
          )}
          {summary.compute_ms != null && (
            <>
              <dt>Simulation</dt>
              <dd>
                {summary.hours} hourly steps in {summary.compute_ms.toFixed(1)} ms
              </dd>
            </>
          )}
          {timing && (
            <>
              <dt>Request</dt>
              <dd>
                {timing.roundTripMs.toFixed(0)} ms round trip · result cache {timing.resultCache ?? "n/a"}
              </dd>
            </>
          )}
          <dt>Slider seek</dt>
          <dd>{seekMicros.toFixed(1)} µs per frame</dd>
        </dl>
        {provenance.attribution && (
          <p className="fine">
            <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
              {provenance.attribution}
            </a>
          </p>
        )}
      </section>
    </aside>
  );
}
