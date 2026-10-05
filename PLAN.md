# LotusLab — Build Plan

LotusLab is an **algorithm-first, weather-driven simulator of a natural lotus pond**.
Pick a place and a date range; the backend pulls real hourly weather from the free
Open-Meteo API, integrates a coupled sun / water / lotus model over every hour, and
hands the browser one compact precomputed timeline. A time slider then scrubs through
that timeline in constant time: sky, sun, rain, water level and lotus cover all follow
the selected minute without another network call.

There is **no database**. State lives in bounded in-memory caches on the server and in
typed arrays in the browser. The engineering focus is the speed and correctness of the
algorithms, not persistence.

## Guiding decisions

| Decision | Choice | Why |
|---|---|---|
| Persistence | None (in-memory TTL/LRU caches) | The product is a computation, not a record store |
| Weather source | Open-Meteo forecast + archive APIs, fetched by FastAPI | Free, no key, hourly variables incl. ET₀ and radiation |
| Pond type | Natural pond: rain, catchment runoff, evaporation, seepage, overflow | Chosen by the project owner |
| Time engine | Precompute hourly states once, seek with O(1) index + interpolation | Slider stays under one frame budget |
| Source of truth | Backend simulation; frontend only interpolates between backend states | Browser and server can never disagree |
| Frontend | React + TypeScript + D3 (SVG) on Vite | React owns UI state, D3 owns scales/charts |
| Offline / demo | Explicit `source=synthetic` weather, always labelled | Never pretend synthetic data is live |

## Phases

Each phase ends with passing tests before the next starts.

### Phase 1 — Simulation core (pure Python, no I/O)
- `solar`: NOAA solar position (elevation, azimuth) vectorised over time; day phase
  classification (night, twilight, golden hour, day).
- `weather`: normalised hourly weather container, validation, gap filling.
- `hydrology`: paraboloid pond bathymetry (closed-form volume ⇄ depth ⇄ area), hourly
  water balance with rain, runoff, open-water evaporation, seepage and overflow, and a
  per-step ledger whose mass balance closes exactly.
- `lotus`: logistic growth with temperature (cardinal beta function), light
  (saturating) and water-depth limitation, solved with the exact logistic step so any
  time step is stable; capacity is the *current* water surface, so a shrinking pond
  squeezes the lotus.
- `classic`: the Day 29 puzzle (pure doubling) as a reference model.
- `engine`: one pass that turns weather into a columnar timeline; `seek(t)` in O(1).
- Tests: mass conservation, overflow cap, monotonic doubling, Day 29, seek equals
  stored state at grid points, invariants under random inputs.

### Phase 2 — FastAPI service and weather adapter
- Async Open-Meteo client (httpx) choosing forecast or archive endpoint by date,
  with timeouts, bounded retries and typed errors.
- TTL + LRU cache with single-flight request coalescing; stale-if-error fallback
  that is reported in the response's provenance block.
- Simulation result cache keyed by (weather key, parameters hash).
- Endpoints: `GET /api/v1/health`, `GET /api/v1/weather`, `GET /api/v1/scenarios`,
  `POST /api/v1/simulations`, `POST /api/v1/simulations/compare`, `GET /api/v1/puzzle`.
- Pydantic validation at the boundary (finite numbers, bounded horizons, valid
  coordinates). Request timing header.
- Tests with a mocked transport; no network needed for CI.

### Phase 3 — Interactive frontend
- Vite + React + TS app; typed API client.
- `Timeline` class over `Float64Array` columns with O(1) `seek(t)`.
- Pond scene (SVG): sky gradient from solar elevation, sun/moon path, stars, clouds
  from cloud cover, rain from precipitation, water surface scaled from area, lotus
  leaves from a precomputed deterministic layout (showing the first N is O(1)).
- D3 charts: depth and lotus cover with a synced cursor, rain bars, water ledger.
- Inspector panel with values at the selected minute and data provenance.

### Phase 4 — Time engine and playback
- Play / pause / speed; playback derives state from simulation time, never from frame
  counts, so frame rate cannot change the outcome.
- Keyboard scrubbing, jump to sunrise / sunset / next rain.

### Phase 5 — What-if laboratory
- Scenario presets (monsoon surge, heatwave, overcast, drought) and custom offsets.
- Live vs what-if comparison with divergence metrics.
- Sensitivity sweep (heatmap of final cover vs rain × temperature offsets).

### Phase 6 — Production quality
- Docker images, CI (pytest, vitest, typecheck, build), structured logging.
- Benchmarks for 30 / 90 / 365-day horizons and seek latency, tracked in the README.

## Model assumptions (summary)

The full list with equations lives in [`docs/MODEL.md`](docs/MODEL.md). Weather data is
real; pond depth and lotus cover are **modelled estimates** until calibrated against
observations of a real pond.
