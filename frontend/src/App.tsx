import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api, type Timing } from "./api/client";
import type { CompareResponse, PondIn, LotusIn, Provenance, SensitivityResponse, SimulationRequest, Summary } from "./api/types";
import { Controls, type FormState } from "./components/Controls";
import { Inspector } from "./components/Inspector";
import { PondScene } from "./components/PondScene";
import { SensitivityMap } from "./components/SensitivityMap";
import { TimelineChart } from "./components/TimelineChart";
import { TimeSlider } from "./components/TimeSlider";
import { PlaybackClock } from "./engine/playback";
import { Timeline, localParts } from "./engine/timeline";

interface Loaded {
  timeline: Timeline;
  summary: Summary;
  provenance: Provenance;
  timing: Timing | null;
  variant: { timeline: Timeline; summary: Summary; label: string } | null;
  divergence: CompareResponse["divergence"] | null;
  seekMicros: number;
  pond: Required<Pick<PondIn, "surface_area_m2">> & { max_depth_m: number };
}

const isoDay = (d: Date) => d.toISOString().slice(0, 10);

const INITIAL: FormState = {
  latitude: 18.52,
  longitude: 73.86,
  start_date: isoDay(new Date(Date.now() - 7 * 86400_000)),
  days: 14,
  source: "auto",
  scenario: { preset: "live" },
  compareWith: "none",
  surface_area_m2: 200,
  initial_depth_m: 1.0,
  catchment_area_m2: 1500,
  initial_cover_fraction: 0.04,
};

export default function App() {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [sensitivity, setSensitivity] = useState<SensitivityResponse | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(3600);
  const clockRef = useRef<PlaybackClock | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const requestBase = useCallback(
    (f: FormState) => {
      const pond: PondIn = { surface_area_m2: f.surface_area_m2, initial_depth_m: f.initial_depth_m, catchment_area_m2: f.catchment_area_m2 };
      const lotus: LotusIn = { initial_cover_fraction: f.initial_cover_fraction };
      return { latitude: f.latitude, longitude: f.longitude, start_date: f.start_date, days: f.days, source: f.source, pond, lotus };
    },
    [],
  );

  const run = useCallback(
    async (f: FormState) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setBusy(true);
      setError(null);
      try {
        const base = requestBase(f);
        let next: Omit<Loaded, "seekMicros">;
        if (f.compareWith !== "none") {
          const { data, timing } = await api.compare({ ...base, baseline: f.scenario, variant: { preset: f.compareWith } }, ctrl.signal);
          next = {
            timeline: new Timeline(data.baseline.timeline),
            summary: data.baseline.summary,
            provenance: data.provenance,
            timing,
            variant: { timeline: new Timeline(data.variant.timeline), summary: data.variant.summary, label: f.compareWith.replace("_", " ") },
            divergence: data.divergence,
            pond: { surface_area_m2: f.surface_area_m2, max_depth_m: 1.5 },
          };
        } else {
          const body: SimulationRequest = { ...base, scenario: f.scenario };
          const { data, timing } = await api.simulate(body, ctrl.signal);
          next = {
            timeline: new Timeline(data.timeline),
            summary: data.summary,
            provenance: data.provenance,
            timing,
            variant: null,
            divergence: null,
            pond: { surface_area_m2: f.surface_area_m2, max_depth_m: 1.5 },
          };
        }
        const seekMicros = measureSeek(next.timeline);
        setLoaded({ ...next, seekMicros });
        const now = performance.now();
        // keep the same wall-clock moment when re-running, else start at local noon of day 0
        const prev = clockRef.current?.at(now);
        const startAt = prev != null && prev >= next.timeline.t0 && prev <= next.timeline.tEnd ? prev : firstNoon(next.timeline, next.provenance.utc_offset_s);
        clockRef.current = new PlaybackClock(startAt, next.timeline.t0, next.timeline.tEnd, speed);
        setTime(startAt);
        setPlaying(false);
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setError(e instanceof ApiError ? { status: e.status, message: e.message } : { status: 0, message: `Could not reach the LotusLab API (${(e as Error).message})` });
      } finally {
        if (abortRef.current === ctrl) setBusy(false);
      }
    },
    [requestBase, speed],
  );

  useEffect(() => {
    void run(INITIAL);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // animation loop: simulation time is derived from the wall clock, never from frame counts
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      const clock = clockRef.current;
      if (!clock) return;
      const now = performance.now();
      setTime(clock.at(now));
      if (clock.ended(now)) {
        clock.pause(now);
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const seek = useCallback((t: number) => {
    const clock = clockRef.current;
    if (!clock) return;
    clock.seek(t, performance.now());
    setTime(clock.at(performance.now()));
  }, []);

  const togglePlay = () => {
    const clock = clockRef.current;
    if (!clock) return;
    const now = performance.now();
    if (clock.playing) clock.pause(now);
    else clock.play(now);
    setPlaying(clock.playing);
  };

  const changeSpeed = (s: number) => {
    setSpeed(s);
    clockRef.current?.setSpeed(s, performance.now());
  };

  const runSensitivity = async () => {
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.sensitivity({
        ...requestBase(form),
        temperature_offsets_c: [-4, -2, 0, 2, 4, 6],
        precipitation_multipliers: [0, 0.5, 1, 2, 3],
      });
      setSensitivity(data);
    } catch (e) {
      setError(e instanceof ApiError ? { status: e.status, message: e.message } : { status: 0, message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const sample = useMemo(() => (loaded ? loaded.timeline.sample(time) : null), [loaded, time]);
  const variantSample = useMemo(() => (loaded?.variant ? loaded.variant.timeline.sample(time) : null), [loaded, time]);
  const offset = loaded?.provenance.utc_offset_s ?? 0;
  const localHour = localParts(time, offset).hour;

  return (
    <div className="app">
      <header>
        <div>
          <h1>LotusLab</h1>
          <p>A natural lotus pond driven by real weather, simulated hour by hour.</p>
        </div>
        {loaded?.provenance.source === "synthetic" && <span className="badge warn">Synthetic weather</span>}
        {loaded?.provenance.stale && <span className="badge warn">Stale weather (provider unreachable)</span>}
      </header>

      <main>
        <Controls form={form} busy={busy} onChange={setForm} onRun={() => run(form)} onSensitivity={runSensitivity} />

        <div className="stage">
          {error && (
            <div className="error" role="alert">
              <strong>{error.status ? `Error ${error.status}` : "Network error"}:</strong> {error.message}
              {(error.status === 503 || error.status === 0) && form.source !== "synthetic" && (
                <button
                  type="button"
                  onClick={() => {
                    const f = { ...form, source: "synthetic" as const };
                    setForm(f);
                    void run(f);
                  }}
                >
                  Use synthetic demo weather
                </button>
              )}
            </div>
          )}

          {loaded && sample ? (
            <>
              <div className={loaded.variant ? "scenes two" : "scenes"}>
                <figure>
                  <PondScene sample={sample} latitude={form.latitude} surfaceAreaFull={loaded.pond.surface_area_m2} localHour={localHour} />
                  <figcaption>{form.scenario.preset === "live" ? "Live weather" : `Scenario: ${form.scenario.preset.replace("_", " ")}`}</figcaption>
                </figure>
                {loaded.variant && variantSample && (
                  <figure>
                    <PondScene sample={variantSample} latitude={form.latitude} surfaceAreaFull={loaded.pond.surface_area_m2} localHour={localHour} label="What-if pond" />
                    <figcaption>What-if: {loaded.variant.label}</figcaption>
                  </figure>
                )}
              </div>

              <TimeSlider
                timeline={loaded.timeline}
                time={time}
                utcOffsetS={offset}
                playing={playing}
                speed={speed}
                onSeek={seek}
                onTogglePlay={togglePlay}
                onSpeed={changeSpeed}
              />

              <TimelineChart
                timeline={loaded.timeline}
                variant={loaded.variant?.timeline}
                milestones={loaded.summary.milestones}
                time={time}
                utcOffsetS={offset}
                maxDepth={loaded.pond.max_depth_m}
                onSeek={seek}
              />

              {loaded.divergence && loaded.variant && (
                <div className="divergence">
                  <strong>Live vs {loaded.variant.label}:</strong> final depth differs by {loaded.divergence.final_depth_delta_m.toFixed(2)} m, lotus cover by{" "}
                  {(loaded.divergence.final_cover_delta * 100).toFixed(1)} points of the pond.{" "}
                  {loaded.divergence.first_divergence_time != null
                    ? `The ponds drift more than ${loaded.divergence.threshold * 100}% apart at ${localParts(loaded.divergence.first_divergence_time, offset).date} ${localParts(loaded.divergence.first_divergence_time, offset).time}.`
                    : "They never drift more than 5% apart."}
                </div>
              )}

              {sensitivity && (
                <SensitivityMap
                  data={sensitivity}
                  onPick={(t, r) => {
                    const f = { ...form, scenario: { ...form.scenario, temperature_offset_c: t, precipitation_multiplier: r } };
                    setForm(f);
                    void run(f);
                  }}
                />
              )}
            </>
          ) : (
            !error && <div className="loading">Fetching weather and simulating…</div>
          )}
        </div>

        {loaded && sample && (
          <Inspector sample={sample} timeline={loaded.timeline} summary={loaded.summary} provenance={loaded.provenance} timing={loaded.timing} seekMicros={loaded.seekMicros} />
        )}
      </main>

      <footer>
        Pond depth and lotus cover are model estimates, not measurements. See docs/MODEL.md for every equation and assumption.
      </footer>
    </div>
  );
}

function firstNoon(tl: Timeline, offset: number): number {
  const local0 = tl.t0 + offset;
  const noon = local0 - (((local0 % 86400) + 86400) % 86400) + 12 * 3600 - offset;
  return tl.clamp(noon < tl.t0 ? noon + 86400 : noon);
}

/** Average cost of one full-state seek on this timeline, measured in the browser. */
function measureSeek(tl: Timeline, n = 2000): number {
  const span = tl.tEnd - tl.t0;
  const started = performance.now();
  let sink = 0;
  for (let i = 0; i < n; i++) sink += tl.sample(tl.t0 + ((i * 7919) % n) * (span / n)).depth_m;
  const us = ((performance.now() - started) * 1000) / n;
  return sink === -1 ? 0 : us;
}
