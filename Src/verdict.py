"""
The verdict layer.

Output is not a binary alert. For each consumer it produces a *trust ratio*: of
the checks that protect the streams this consumer depends on, how many held -
weighted by severity - plus the blast radius and an estimated clear-by time. This
is what turns 'something moved' into 'here is how much to trust this report, why,
and until when'.

Deterministic by construction: the verdict is a count over falsifiable checks, not
a model's opinion. Soft signals can propose; the count decides.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
from .checks import Finding
from .checks import CHECK_COST_UNITS
from .triage import DETECTION_SEVERITY
from .lineage import Consumer


@dataclass
class Verdict:
    consumer_id: str
    trust: float                 # 0..1 severity-weighted pass ratio
    blast: float
    failed: List[str]
    clear_by_minutes: float
    headline: str


# rough time-to-clear per check type once a fault is raised
CLEAR_MINUTES = {
    "freshness": 30,
    "completeness_global": 60,
    "completeness_conditional": 90,
    "tail_percentiles": 120,
}


def consumer_verdict(consumer: Consumer, findings: List[Finding]) -> Verdict:
    relevant = [f for f in findings if f.stream_id in consumer.reads]
    if not relevant:
        return Verdict(consumer.id, 1.0, consumer.criticality, [], 0.0, "no checks mapped")

    num = den = 0.0
    failed = []
    clear = 0.0
    for f in relevant:
        w = DETECTION_SEVERITY.get(f.check, 1.0)
        den += w
        if f.passed:
            num += w
        else:
            failed.append(f"{f.stream_id}:{f.check} ({f.reason})")
            clear = max(clear, CLEAR_MINUTES.get(f.check, 60))
    trust = num / den if den else 1.0

    if trust >= 0.999:
        head = "TRUSTED - all protecting checks held"
    elif trust >= 0.7:
        head = "DEGRADED - usable with caution"
    else:
        head = "DO NOT TRUST - material checks failed"

    return Verdict(consumer.id, trust, consumer.criticality, failed, clear, head)
