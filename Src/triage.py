"""
The triage engine - the headline.

Checking everything, every 15 minutes, at p99, is the brute-force baseline. It is
also expensive and it bottlenecks ingestion. The question this engine answers is
not 'is the data good' but:

    Given a finite QA budget, WHICH checks, on WHICH streams, at WHAT cadence,
    are worth running - so that the spend lands where the blast radius justifies
    it and nowhere else?

Decision per (stream, check):
  value  = blast_radius x prior_fault_rate x detection_severity
  cost   = check_cost_units x volume x runs_per_month(cadence)
  keep the *cheapest cadence whose value still clears its cost*, drop otherwise.

Two hard rules encode the domain:
  - The expensive tail-percentile check is only scheduled on streams that feed a
    tail-sensitive consumer. (Targeted expensive statistics.)
  - Conditional/MNAR checks run at a cadence no finer than needed to bound the
    window of undetected corruption against blast radius.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
from .streams import Stream, GRAIN_RUNS_PER_MONTH
from .checks import CHECK_COST_UNITS
from .lineage import Consumer, blast_radius, feeds_tail_sensitive

# cadence -> runs/month
CADENCE_RUNS = {
    "15min": GRAIN_RUNS_PER_MONTH["15min"],
    "hourly": GRAIN_RUNS_PER_MONTH["hourly"],
    "daily": GRAIN_RUNS_PER_MONTH["daily"],
    "off": 0,
}
CADENCE_ORDER = ["off", "daily", "hourly", "15min"]

# prior likelihood a given check type finds something, and how bad it is if missed
PRIOR_FAULT_RATE = {
    "freshness": 0.30,
    "completeness_global": 0.15,
    "completeness_conditional": 0.20,
    "tail_percentiles": 0.18,
}
DETECTION_SEVERITY = {
    "freshness": 1.0,
    "completeness_global": 1.2,
    "completeness_conditional": 2.5,   # silent MNAR is dangerous
    "tail_percentiles": 2.0,
}


@dataclass
class Decision:
    stream_id: str
    check: str
    cadence: str
    monthly_cost: float
    value_score: float
    rationale: str


def _check_cost(stream: Stream, check: str, cadence: str, dollars_per_unit: float) -> float:
    runs = CADENCE_RUNS[cadence]
    return CHECK_COST_UNITS[check] * stream.volume * runs * dollars_per_unit


def baseline_everything_cost(streams: List[Stream], dollars_per_unit: float) -> float:
    """Brute force: every check, every stream, at 15-min cadence."""
    total = 0.0
    for s in streams:
        for check in CHECK_COST_UNITS:
            total += _check_cost(s, check, "15min", dollars_per_unit)
    return total


def triage(streams: List[Stream], consumers: List[Consumer],
           dollars_per_unit: float, value_per_blast_point: float = 900.0) -> List[Decision]:
    decisions: List[Decision] = []
    for s in streams:
        br = blast_radius(s, consumers)
        tail_ok = feeds_tail_sensitive(s, consumers)
        for check in CHECK_COST_UNITS:
            # Rule 1: expensive tail check only where a tail-sensitive consumer exists
            if check == "tail_percentiles" and not tail_ok:
                decisions.append(Decision(
                    s.id, check, "off", 0.0, 0.0,
                    f"skip p99: no tail-sensitive downstream (blast {br:.0f})"))
                continue

            value = (br * value_per_blast_point
                     * PRIOR_FAULT_RATE[check] * DETECTION_SEVERITY[check])

            # choose the cheapest cadence whose value clears its cost; prefer
            # finer cadence only when value strongly dominates cost.
            chosen, chosen_cost = "off", 0.0
            for cadence in ["daily", "hourly", "15min"]:
                cost = _check_cost(s, check, cadence, dollars_per_unit)
                if value >= cost:
                    chosen, chosen_cost = cadence, cost
                else:
                    break  # finer cadences only get more expensive

            if chosen == "off":
                rationale = f"skip: blast {br:.0f} too low to justify cost"
            else:
                rationale = (f"blast {br:.0f}"
                             + (", tail-sensitive" if (check == 'tail_percentiles') else "")
                             + f" -> {chosen} (value {value:,.0f} >= cost {chosen_cost:,.0f})")
            decisions.append(Decision(s.id, check, chosen, chosen_cost, value, rationale))
    return decisions


def plan_cost(decisions: List[Decision]) -> float:
    return sum(d.monthly_cost for d in decisions)
