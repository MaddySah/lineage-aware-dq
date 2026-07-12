"""
Lineage and blast radius.

The reason we can triage at all is that not every stream matters equally. A
stream's importance is not intrinsic - it is *inherited from what depends on it*.
Blast radius = the criticality-weighted count of downstream consumers reached.

This is the same idea as 'downstream dependents x criticality' used to rank risk
in dependency graphs generally; here it decides where QA spend is justified.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
from .streams import Stream


@dataclass
class Consumer:
    id: str
    criticality: float           # 1=internal nice-to-have ... 5=revenue/regulatory
    reads: List[str]             # stream ids
    tail_sensitive: bool = False  # does it actually consume tail latency metrics?


def default_consumers() -> List[Consumer]:
    return [
        Consumer("revenue_dashboard", 5.0, ["billing_rollup_daily", "session_events_log"]),
        Consumer("sla_alerting", 5.0, ["edge_latency_15m", "network_health_hourly"], tail_sensitive=True),
        Consumer("capacity_planning", 3.0, ["network_health_hourly", "device_telemetry_15m"]),
        Consumer("exec_weekly_report", 4.0, ["billing_rollup_daily"]),
        Consumer("support_ops_view", 1.0, ["support_tickets_hourly"]),
    ]


def wire_lineage(streams: List[Stream], consumers: List[Consumer]) -> None:
    by_id = {s.id: s for s in streams}
    for c in consumers:
        for sid in c.reads:
            if sid in by_id:
                by_id[sid].consumers.append(c.id)


def blast_radius(stream: Stream, consumers: List[Consumer]) -> float:
    """Criticality-weighted reach of a stream."""
    cmap = {c.id: c for c in consumers}
    return sum(cmap[cid].criticality for cid in stream.consumers if cid in cmap)


def feeds_tail_sensitive(stream: Stream, consumers: List[Consumer]) -> bool:
    cmap = {c.id: c for c in consumers}
    return any(cmap[cid].tail_sensitive for cid in stream.consumers if cid in cmap)
