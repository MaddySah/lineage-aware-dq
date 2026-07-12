"""
The detection layer.

Four detectors, deliberately split into the cheap-and-shallow vs the
expensive-and-sharp, because the whole thesis of this project is that the second
kind must be *targeted*, not run everywhere.

  - freshness        : cheap. is the stream still arriving on time.
  - completeness_global : cheap. overall row volume sane. THIS IS THE ONE THAT
                          LIES - it stays green through a segment-level MNAR gap.
  - completeness_conditional (MNAR) : moderate. checks completeness PER SEGMENT.
                          catches the silent hole the global check misses.
  - tail_percentiles : expensive. p50/p90/p95/p99. catches tail drift that any
                          mean-based monitor is blind to. Cost is why it must be
                          triaged onto only the streams that feed tail-sensitive
                          consumers.

Each detector returns a Finding with pass/fail and a short, human reason.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
from .streams import Window

# relative compute cost per run, in abstract units. Converted to $ later.
CHECK_COST_UNITS = {
    "freshness": 0.1,
    "completeness_global": 0.5,
    "completeness_conditional": 2.0,
    "tail_percentiles": 5.0,     # percentiles over raw samples are the costly one
}


@dataclass
class Finding:
    stream_id: str
    check: str
    passed: bool
    reason: str
    detail: Optional[dict] = None


def check_freshness(w: Window, sla_minutes: float) -> Finding:
    ok = w.minutes_since_refresh <= sla_minutes
    return Finding(
        w.stream_id, "freshness", ok,
        f"{w.minutes_since_refresh:.0f}m since refresh (SLA {sla_minutes:.0f}m)",
    )


def check_completeness_global(w: Window, floor_ratio: float = 0.80) -> Finding:
    total = sum(w.rows_by_segment.values())
    expected = 1000 + 800 + 600 + 500
    ratio = total / expected
    ok = ratio >= floor_ratio
    return Finding(
        w.stream_id, "completeness_global", ok,
        f"overall volume {ratio:.1%} of expected",
        {"ratio": ratio},
    )


def check_completeness_conditional(w: Window, floor_ratio: float = 0.5) -> Finding:
    """Per-segment completeness. Catches MNAR holes the global check hides."""
    base = {"north": 1000, "south": 800, "east": 600, "west": 500}
    dead = []
    for seg in w.expected_segments:
        exp = base.get(seg, 1)
        got = w.rows_by_segment.get(seg, 0)
        if got / exp < floor_ratio:
            dead.append(seg)
    ok = len(dead) == 0
    reason = "all segments reporting" if ok else f"segment(s) dark: {', '.join(dead)}"
    return Finding(
        w.stream_id, "completeness_conditional", ok, reason, {"dead_segments": dead}
    )


def check_tail_percentiles(w: Window, p99_ceiling: float = 130.0) -> Finding:
    """p50/p90/p95/p99. Catches tail drift invisible to the mean."""
    s = w.latency_samples
    p = {
        "mean": float(np.mean(s)),
        "p50": float(np.percentile(s, 50)),
        "p90": float(np.percentile(s, 90)),
        "p95": float(np.percentile(s, 95)),
        "p99": float(np.percentile(s, 99)),
    }
    ok = p["p99"] <= p99_ceiling
    reason = (
        f"p99={p['p99']:.0f}ms (ceiling {p99_ceiling:.0f}) "
        f"| mean={p['mean']:.0f} p50={p['p50']:.0f} look fine"
    )
    return Finding(w.stream_id, "tail_percentiles", ok, reason, p)
