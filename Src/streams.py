"""
Dummy multi-grain telemetry generator with *planted* faults.

The point of this module is not realism for its own sake. It produces streams at
several grains (15-min, hourly, daily, log) and deliberately injects three faults
that ordinary aggregate checks cannot see:

  1. Segment-level MNAR gap  - one segment silently stops reporting. Global
     completeness still looks healthy (~99%); only a *conditional* (per-segment)
     check reveals the hole.
  2. Tail-distribution drift  - p99 latency degrades while the mean and p50 stay
     flat. Invisible to any average-based monitor; only a targeted percentile
     check catches it.
  3. Freshness lag  - a stream stops refreshing. Cheap to detect *if* you check
     the right stream; wasteful to check everywhere.

Every planted fault is labelled so the demo can prove what was caught vs missed.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np

RNG = np.random.default_rng(7)

GRAIN_RUNS_PER_MONTH = {
    "15min": 4 * 24 * 30,   # 2880
    "hourly": 24 * 30,      # 720
    "daily": 30,            # 30
    "log": 6 * 24 * 30,     # event-ish, treated as high volume
}

# relative data volume per run, by grain (finer grain = more rows per window)
GRAIN_VOLUME = {"15min": 4.0, "hourly": 2.0, "daily": 1.0, "log": 6.0}


@dataclass
class Stream:
    id: str
    grain: str
    segments: List[str]
    # which downstream consumers read this stream (filled from lineage)
    consumers: List[str] = field(default_factory=list)
    # planted-fault flags (ground truth, for scoring the demo)
    planted: Dict[str, bool] = field(default_factory=dict)

    @property
    def volume(self) -> float:
        return GRAIN_VOLUME[self.grain]


@dataclass
class Window:
    """One observation window of a stream's telemetry."""
    stream_id: str
    rows_by_segment: Dict[str, int]
    latency_samples: np.ndarray          # for percentile checks
    expected_segments: List[str]
    minutes_since_refresh: float


def build_streams() -> List[Stream]:
    seg = ["north", "south", "east", "west"]
    return [
        Stream("edge_latency_15m", "15min", seg,
               planted={"tail_drift": True}),                 # p99 degrades, mean flat
        Stream("session_events_log", "log", seg,
               planted={"mnar_segment": True}),               # 'west' goes dark
        Stream("billing_rollup_daily", "daily", seg,
               planted={}),                                    # clean
        Stream("network_health_hourly", "hourly", seg,
               planted={"freshness_lag": True}),              # stops refreshing
        Stream("device_telemetry_15m", "15min", seg,
               planted={}),                                    # clean
        Stream("support_tickets_hourly", "hourly", seg,
               planted={}),                                    # clean, low criticality
    ]


def generate_window(stream: Stream, faulted: bool) -> Window:
    """Generate one window. If faulted=True, planted faults are active."""
    base_rows = {"north": 1000, "south": 800, "east": 600, "west": 500}

    rows = dict(base_rows)
    if faulted and stream.planted.get("mnar_segment"):
        # 'west' (the smallest segment) silently drops to a trickle. Global total
        # falls only ~16% -> still above the 85% floor, so the aggregate monitor
        # stays GREEN. The hole is visible only when you check completeness PER
        # SEGMENT. This is the silent MNAR case aggregate checks cannot see.
        rows["west"] = 40  # was 500; ~16% of the 2900 total

    # latency distribution: normal body, heavy tail
    n = 5000
    body = RNG.normal(40, 8, n)              # mean ~40ms
    tail = RNG.pareto(3.0, n) * 15 + 60      # heavy tail
    mix = np.where(RNG.random(n) < 0.92, body, tail)
    if faulted and stream.planted.get("tail_drift"):
        # degrade ONLY the extreme tail; mean & p50 stay put
        k = int(n * 0.03)
        idx = RNG.choice(n, k, replace=False)
        mix[idx] = mix[idx] * 2.4 + 80
    latency = np.clip(mix, 1, None)

    minutes_since = 5.0
    if faulted and stream.planted.get("freshness_lag"):
        minutes_since = 220.0                # way past its hourly SLA

    return Window(
        stream_id=stream.id,
        rows_by_segment=rows,
        latency_samples=latency,
        expected_segments=stream.segments,
        minutes_since_refresh=minutes_since,
    )
