import type {
  CompareRequest,
  CompareResponse,
  SensitivityRequest,
  SensitivityResponse,
  SimulationRequest,
  SimulationResponse,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<{ data: T; timing: Timing }> {
  const started = performance.now();
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const err = await res.json();
      detail = typeof err.detail === "string" ? err.detail : err.detail.map((e: { loc: string[]; msg: string }) => `${e.loc.slice(1).join(".")}: ${e.msg}`).join("; ");
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  const data = (await res.json()) as T;
  return {
    data,
    timing: {
      roundTripMs: performance.now() - started,
      serverMs: Number(res.headers.get("X-Response-Time-Ms") ?? NaN),
      resultCache: res.headers.get("X-Result-Cache"),
      weatherCache: res.headers.get("X-Weather-Cache"),
    },
  };
}

export interface Timing {
  roundTripMs: number;
  serverMs: number;
  resultCache: string | null;
  weatherCache: string | null;
}

export const api = {
  simulate: (body: SimulationRequest, signal?: AbortSignal) => post<SimulationResponse>("/simulations", body, signal),
  compare: (body: CompareRequest, signal?: AbortSignal) => post<CompareResponse>("/simulations/compare", body, signal),
  sensitivity: (body: SensitivityRequest, signal?: AbortSignal) =>
    post<SensitivityResponse>("/simulations/sensitivity", body, signal),
};
