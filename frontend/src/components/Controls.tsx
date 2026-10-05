import type { PresetName, ScenarioIn, Source } from "../api/types";

export interface FormState {
  latitude: number;
  longitude: number;
  start_date: string;
  days: number;
  source: Source;
  scenario: ScenarioIn;
  compareWith: PresetName | "none";
  surface_area_m2: number;
  initial_depth_m: number;
  catchment_area_m2: number;
  initial_cover_fraction: number;
}

export const PLACES: Array<{ name: string; lat: number; lon: number }> = [
  { name: "Pune, India", lat: 18.52, lon: 73.86 },
  { name: "Kolkata, India", lat: 22.57, lon: 88.36 },
  { name: "Hangzhou, China", lat: 30.27, lon: 120.16 },
  { name: "Hanoi, Vietnam", lat: 21.03, lon: 105.85 },
  { name: "Bangkok, Thailand", lat: 13.76, lon: 100.5 },
  { name: "Kyoto, Japan", lat: 35.01, lon: 135.77 },
  { name: "Brisbane, Australia", lat: -27.47, lon: 153.03 },
  { name: "London, UK", lat: 51.51, lon: -0.13 },
];

const PRESET_LABELS: Record<PresetName, string> = {
  live: "Live weather",
  monsoon_surge: "Monsoon surge",
  heatwave: "Heatwave",
  overcast: "Persistent overcast",
  drought: "Drought",
};

interface Props {
  form: FormState;
  busy: boolean;
  onChange: (f: FormState) => void;
  onRun: () => void;
  onSensitivity: () => void;
}

export function Controls({ form, busy, onChange, onRun, onSensitivity }: Props) {
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => onChange({ ...form, [k]: v });
  const setScenario = (patch: Partial<ScenarioIn>) => onChange({ ...form, scenario: { ...form.scenario, ...patch } });
  const place = PLACES.find((p) => p.lat === form.latitude && p.lon === form.longitude)?.name ?? "custom";

  return (
    <form
      className="controls"
      onSubmit={(e) => {
        e.preventDefault();
        onRun();
      }}
    >
      <fieldset>
        <legend>Where and when</legend>
        <label>
          Place
          <select
            value={place}
            onChange={(e) => {
              const p = PLACES.find((x) => x.name === e.currentTarget.value);
              if (p) onChange({ ...form, latitude: p.lat, longitude: p.lon });
            }}
          >
            {PLACES.map((p) => (
              <option key={p.name}>{p.name}</option>
            ))}
            <option value="custom">Custom coordinates</option>
          </select>
        </label>
        <div className="row">
          <label>
            Latitude
            <input type="number" step="any" min={-90} max={90} value={form.latitude} onChange={(e) => set("latitude", Number(e.currentTarget.value))} />
          </label>
          <label>
            Longitude
            <input type="number" step="any" min={-180} max={180} value={form.longitude} onChange={(e) => set("longitude", Number(e.currentTarget.value))} />
          </label>
        </div>
        <div className="row">
          <label>
            Start date
            <input type="date" value={form.start_date} onChange={(e) => set("start_date", e.currentTarget.value)} />
          </label>
          <label>
            Days
            <input type="number" min={1} max={366} value={form.days} onChange={(e) => set("days", Number(e.currentTarget.value))} />
          </label>
        </div>
        <label>
          Weather
          <select value={form.source} onChange={(e) => set("source", e.currentTarget.value as Source)}>
            <option value="auto">Real (Open-Meteo forecast or archive)</option>
            <option value="synthetic">Synthetic demo (offline, labelled)</option>
          </select>
        </label>
      </fieldset>

      <fieldset>
        <legend>What if?</legend>
        <label>
          Scenario
          <select value={form.scenario.preset} onChange={(e) => onChange({ ...form, scenario: { preset: e.currentTarget.value as PresetName } })}>
            {Object.entries(PRESET_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <Slider label="Temperature offset" unit="°C" min={-10} max={10} step={0.5} value={form.scenario.temperature_offset_c} onChange={(v) => setScenario({ temperature_offset_c: v })} />
        <Slider label="Rain multiplier" unit="×" min={0} max={5} step={0.1} value={form.scenario.precipitation_multiplier} onChange={(v) => setScenario({ precipitation_multiplier: v })} />
        <Slider label="Cloud offset" unit="%" min={-100} max={100} step={5} value={form.scenario.cloud_cover_offset_pct} onChange={(v) => setScenario({ cloud_cover_offset_pct: v })} />
        <label>
          Compare against
          <select value={form.compareWith} onChange={(e) => set("compareWith", e.currentTarget.value as FormState["compareWith"])}>
            <option value="none">Nothing</option>
            {Object.entries(PRESET_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      <fieldset>
        <legend>Pond</legend>
        <div className="row">
          <label>
            Surface (m²)
            <input type="number" min={1} value={form.surface_area_m2} onChange={(e) => set("surface_area_m2", Number(e.currentTarget.value))} />
          </label>
          <label>
            Catchment (m²)
            <input type="number" min={0} value={form.catchment_area_m2} onChange={(e) => set("catchment_area_m2", Number(e.currentTarget.value))} />
          </label>
        </div>
        <div className="row">
          <label>
            Start depth (m)
            <input type="number" min={0} max={1.5} step="any" value={form.initial_depth_m} onChange={(e) => set("initial_depth_m", Number(e.currentTarget.value))} />
          </label>
          <label>
            Start lotus cover
            <input type="number" min={0.001} max={0.9} step="any" value={form.initial_cover_fraction} onChange={(e) => set("initial_cover_fraction", Number(e.currentTarget.value))} />
          </label>
        </div>
      </fieldset>

      <div className="actions">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Simulating…" : "Run simulation"}
        </button>
        <button type="button" onClick={onSensitivity} disabled={busy}>
          Sensitivity map
        </button>
      </div>
    </form>
  );
}

function Slider(props: { label: string; unit: string; min: number; max: number; step: number; value: number | null | undefined; onChange: (v: number | null) => void }) {
  const active = props.value != null;
  return (
    <label className="slider">
      <span>
        {props.label}
        <output>{active ? `${props.value}${props.unit}` : "preset"}</output>
        {active && (
          <button type="button" className="link" onClick={() => props.onChange(null)}>
            reset
          </button>
        )}
      </span>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value ?? (props.min + props.max) / 2}
        onChange={(e) => props.onChange(Number(e.currentTarget.value))}
      />
    </label>
  );
}
