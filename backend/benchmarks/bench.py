"""Micro-benchmarks for the simulation core and the HTTP hot path.

    python -m benchmarks.bench            # from backend/

Prints a Markdown table. Numbers are machine dependent; compare runs on one machine.
"""

from __future__ import annotations

import platform
import statistics
import time
from collections.abc import Callable

import numpy as np

from lotuslab.core import synthetic
from lotuslab.core.engine import simulate
from lotuslab.core.scenarios import PRESETS, apply
from lotuslab.services.simulation import Encoded, encode, run_payload

LAT, LON = 18.52, 73.86
T0 = 1751328000.0


def timeit(fn: Callable[[], object], repeat: int = 15, number: int = 1) -> float:
    """Median wall time per call in milliseconds."""
    fn()  # warm-up
    samples = []
    for _ in range(repeat):
        t = time.perf_counter()
        for _ in range(number):
            fn()
        samples.append((time.perf_counter() - t) * 1000.0 / number)
    return statistics.median(samples)


def main() -> None:
    rows: list[tuple[str, str]] = []
    for days in (30, 90, 365):
        w = synthetic.generate(T0, days * 24, LAT, LON)
        rows.append((f"simulate {days} days ({days * 24} hourly steps)", f"{timeit(lambda: simulate(w, LAT, LON)):.2f} ms"))

    w = synthetic.generate(T0, 365 * 24, LAT, LON)
    tl = simulate(w, LAT, LON)
    rng = np.random.default_rng(0)
    ts = (tl.t0 + rng.random(10_000) * (tl.t_end - tl.t0)).tolist()

    def seeks() -> None:
        for t in ts:
            tl.seek(t)

    per_seek_us = timeit(seeks, repeat=5) * 1000.0 / len(ts)
    rows.append(("seek(t) on a 365-day timeline (all columns)", f"{per_seek_us:.2f} µs"))

    def between() -> None:
        for t in ts:
            tl.between("rain_m3", tl.t0, t)

    rows.append(("rain total between two instants (prefix sums)", f"{timeit(between, repeat=5) * 1000.0 / len(ts):.2f} µs"))

    w30 = synthetic.generate(T0, 30 * 24, LAT, LON)
    rows.append(
        (
            "all 5 scenario presets, 30 days",
            f"{timeit(lambda: [simulate(apply(w30, s), LAT, LON) for _, s in PRESETS.values()]):.2f} ms",
        )
    )
    tl30 = simulate(w30, LAT, LON)
    rows.append(("serialise 30-day timeline to JSON + gzip", f"{timeit(lambda: Encoded.of(encode(run_payload(tl30, PRESETS['live'][1])))):.2f} ms"))
    size = len(Encoded.of(encode(run_payload(tl30, PRESETS["live"][1]))).gz)
    rows.append(("30-day payload size (gzip)", f"{size / 1024:.0f} KiB"))

    print(f"Python {platform.python_version()} · numpy {np.__version__} · {platform.machine()}\n")
    print("| Operation | Median |\n|---|---|")
    for name, value in rows:
        print(f"| {name} | {value} |")


if __name__ == "__main__":
    main()
