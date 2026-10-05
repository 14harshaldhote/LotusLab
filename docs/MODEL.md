# LotusLab model

This page lists every equation and assumption the simulator uses. Weather inputs are
real (Open-Meteo) or explicitly synthetic. Everything downstream of the weather (soil
moisture, pond depth, lotus cover) is a **model estimate**, not a measurement, until it is
calibrated against observations of a real pond.

## Time grid

* Regular hourly grid in UTC (`dt = 3600 s`).
* Row 0 is the initial condition. Row *k* is the state at `time[k]` after applying the
  weather of the hour ending at `time[k]` (Open-Meteo reports precipitation and radiation
  over the preceding hour, so this matches the data).
* Between rows the frontend and `Timeline.seek` interpolate linearly. Azimuth is
  unwrapped first so interpolation never swings the sun the long way round.

## Sun

NOAA solar position algorithm (Meeus-based), vectorised over the whole series, with
NOAA's piecewise refraction correction. Day phase from sun elevation *e*:

| Phase | Elevation |
|---|---|
| Night | e < -6° |
| Twilight (dawn / dusk) | -6° ≤ e < 0° |
| Golden hour | 0° ≤ e < 6° |
| Day | e ≥ 6° |

Dawn vs dusk is the sign of the hour angle (negative = morning).

## Pond geometry

Natural bowl modelled as a paraboloid with brim area *A* and spill depth *H*:

```
area(h)   = A h / H
volume(h) = A h² / (2H)
depth(V)  = √(2 V H / A)
```

Closed form both ways, so no root finding per step.

## Catchment runoff

A single soil bucket of capacity *S* (mm) on the catchment of area *A_c*:

```
coeff   = c_dry + (c_wet - c_dry) · (s / S)
quick   = P · coeff
s      += P - quick
excess  = max(s - S, 0)        → also runs off
runoff  = quick + excess
s       = s - drain·dt          (each hour, floored at 0)
```

After a dry spell the first rain mostly soaks in; on wet soil most of it runs off.

## Water balance (per hour)

```
rain_in   = P · A                          rain falls on the whole basin footprint
runoff_in = runoff · A_c
evap      = k_w · ET₀ · area(h)            k_w ≈ 1.05 open water vs reference crop
seep      = seepage_rate · area(h)
V'        = V + rain_in + runoff_in - evap - seep   (losses scaled so V' ≥ 0)
overflow  = max(V' - V_full, 0)
V         = V' - overflow
```

Every flux is stored per row, so the mass balance closes to floating-point precision and
is reported as `mass_balance_error_m3` in every summary. Prefix sums of each flux give the
total between any two instants in O(1).

## Lotus cover

Logistic growth with a moving capacity equal to the current water surface:

```
r(t)   = r_max · f_T(T) · f_L(I) · f_W(h)
K(t)   = k_max · area(h)
C(t+dt) = K C e^{r dt} / (K + C (e^{r dt} - 1))     exact logistic step
C      *= exp(-m dt)                                 mortality
C       = min(C, K)                                  leaves stranded by a falling pond
```

* `f_T`: Yan & Hunt (1999) beta function with cardinal temperatures 12 / 30 / 42 °C.
* `f_L`: saturating light response `I / (I + I_half)`, normalised to 1 at 1000 W/m².
  It is zero at night, so growth only happens in daylight.
* `f_W`: trapezoid in water depth (0 below 0.15 m or above 2.5 m, 1 between 0.4 and 1.6 m).
* `m`: background mortality, plus extra mortality when rhizomes are exposed (depth below
  the minimum) or air temperature exceeds `t_max`.

`saturation = C / K` is how full the pond is in the puzzle's sense. The milestones
`cover_25`, `cover_50`, `cover_full` report when saturation first reaches 25 %, 50 % and
98 %.

## What-if scenarios

Scenarios perturb the real series rather than inventing one:

* temperature offset, with ET₀ scaled by +3 % per °C;
* precipitation multiplier;
* cloud cover offset, with shortwave radiation rescaled by the Kasten–Czeplak cloud
  factor `1 - 0.75 (N)^3.4` and the radiation-driven share of ET₀ following it;
* wind multiplier, with ET₀ scaled by 0.35 × the relative change.

## Classic puzzle

`C_d = min(A, C₀ rᵈ)` and `d_full = ⌈ln(A/C₀) / ln r⌉`. With daily doubling the pond is
half full exactly one day before it is full.

## Known limitations

* No water temperature model; air temperature drives growth directly.
* Lotus transpiration and leaf shading of evaporation are ignored.
* Parameter defaults are plausible, not calibrated.
