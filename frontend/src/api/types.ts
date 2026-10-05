// Contracts mirrored from backend/lotuslab/api/schemas.py.

export type PresetName = "live" | "monsoon_surge" | "heatwave" | "overcast" | "drought";
export type Source = "auto" | "synthetic";

export interface ScenarioIn {
  preset: PresetName;
  temperature_offset_c?: number | null;
  precipitation_multiplier?: number | null;
  cloud_cover_offset_pct?: number | null;
  wind_multiplier?: number | null;
}

export interface PondIn {
  surface_area_m2?: number;
  max_depth_m?: number;
  initial_depth_m?: number;
  catchment_area_m2?: number;
}

export interface LotusIn {
  initial_cover_fraction?: number;
  max_growth_per_day?: number;
}

export interface LocationIn {
  latitude: number;
  longitude: number;
  start_date: string; // YYYY-MM-DD
  days: number;
  source: Source;
  seed?: number;
}

export interface SimulationRequest extends LocationIn {
  scenario: ScenarioIn;
  pond?: PondIn;
  lotus?: LotusIn;
}

export interface CompareRequest extends LocationIn {
  baseline: ScenarioIn;
  variant: ScenarioIn;
  pond?: PondIn;
  lotus?: LotusIn;
}

export interface SensitivityRequest extends LocationIn {
  temperature_offsets_c: number[];
  precipitation_multipliers: number[];
  pond?: PondIn;
  lotus?: LotusIn;
}

export interface Provenance {
  source: "open-meteo-forecast" | "open-meteo-archive" | "synthetic";
  fetched_at: number;
  stale: boolean;
  cache: "hit" | "miss" | "stale";
  timezone: string;
  utc_offset_s: number;
  latitude: number;
  longitude: number;
  gaps_filled: Record<string, number>;
  attribution: string | null;
}

export interface TimelinePayload {
  t0: number;
  dt: number;
  n: number;
  columns: Record<string, number[]>;
  phase: number[];
}

export interface Milestones {
  cover_25: number | null;
  cover_50: number | null;
  cover_full: number | null;
  first_overflow: number | null;
  first_stranded: number | null;
}

export interface Summary {
  hours: number;
  start: number;
  end: number;
  initial_depth_m: number;
  final_depth_m: number;
  min_depth_m: number;
  max_depth_m: number;
  final_cover_fraction: number;
  final_saturation: number;
  peak_saturation: number;
  totals_m3: Record<string, number>;
  mass_balance_error_m3: number;
  overflow_hours: number;
  volume_full_m3: number;
  milestones: Milestones;
  compute_ms?: number;
}

export interface Run {
  scenario: Record<string, number>;
  timeline: TimelinePayload;
  summary: Summary;
}

export interface SimulationResponse extends Run {
  model_version: string;
  provenance: Provenance;
}

export interface CompareResponse {
  model_version: string;
  provenance: Provenance;
  baseline: Run;
  variant: Run;
  divergence: {
    threshold: number;
    first_divergence_time: number | null;
    max_cover_gap: number;
    max_cover_gap_time: number;
    max_depth_gap_m: number;
    final_cover_delta: number;
    final_depth_delta_m: number;
    overflow_delta_m3: number;
  };
}

export interface SensitivityResponse {
  model_version: string;
  provenance: Provenance;
  temperature_offsets_c: number[];
  precipitation_multipliers: number[];
  final_cover_fraction: number[][];
  final_saturation: number[][];
  final_depth_m: number[][];
  overflow_m3: number[][];
  compute_ms: number;
}
