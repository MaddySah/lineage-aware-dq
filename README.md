# Lineage-Aware Data Quality: Triaged Validation for Multi-Grain Telemetry

**The question this answers is not "is the data good." It's "given a finite QA
budget, *which* checks, on *which* streams, at *what* cadence, are worth running."**

Checking everything, every 15 minutes, at p99, is the brute-force baseline. In a
real multi-grain telemetry environment that bill runs to **~$68k/month** and it
bottlenecks ingestion. The opposite extreme is the *scream test*: ship the data
and wait for someone downstream to scream. One is expensive always; the other is
catastrophic exactly when it matters.

This project lives in between. It walks the **lineage** to learn what each stream's
blast radius actually is, then spends QA compute **only where the blast radius
justifies it** — catching the silent faults that aggregate monitoring misses, at a
fraction of the cost.

```
Triaged plan: $9,960/mo   vs   brute-force baseline: $68,000/mo   ->   85% saved
...while catching 2 silent faults the cheap aggregate monitor reported as GREEN.
```

## Quickstart

```bash
git clone https://github.com/MaddySah/lineage-aware-dq.git
cd lineage-aware-dq
pip install -r requirements.txt      # numpy only
python -m src.demo                    # plants the faults and catches them, end to end
```

No API keys, no external services, no data to download. Runs in seconds on synthetic
telemetry with *planted* faults, so every number above is reproducible on your machine.

---

---

## Why aggregate monitoring lies

Two faults that ordinary average-and-total checks **cannot** see, both caught here:

1. **Segment-level MNAR gap.** One segment silently stops reporting. The *global*
   completeness check stays green (overall volume still ~84%, above floor) while a
   whole segment is dark. Only a **conditional, per-segment** check finds the hole.
   Missingness is not random, and the shape of what's missing is itself the signal.

2. **Tail-distribution drift.** p99 latency degrades while the **mean and p50 stay
   flat**. Invisible to any average-based monitor. Aggregations water down exactly
   the detail you need, so the tail percentiles (p50/p90/p95/p99) have to be kept
   sharp — and because percentiles over raw samples are *expensive*, they must be
   **targeted**, not run everywhere.

The demo output, verbatim:

```
ACT 3  -  NAIVE AGGREGATE CHECKS  (cheap, and they LIE)
  session_events_log       OK       (overall volume 84.1% of expected)   <- GREEN, but 'west' is dark
  ...
  >> Aggregate monitor says mostly GREEN. But it silently missed:
       - edge_latency_15m: p99 tail drift
       - session_events_log: segment-level MNAR gap

ACT 5  -  TARGETED CHECKS RUN  (catch what aggregates hid)
  [CAUGHT] edge_latency_15m: tail_percentiles -> p99=188ms (ceiling 130) | mean=46 p50=41 look fine
  [CAUGHT] session_events_log: completeness_conditional -> segment(s) dark: west
  [CAUGHT] network_health_hourly: freshness -> 220m since refresh (SLA 90m)
```

---

## The triage engine (the headline)

Importance is **inherited, not intrinsic**: a stream matters because of what
depends on it. Blast radius = criticality-weighted count of downstream consumers.

For each `(stream, check)` the engine computes:

```
value = blast_radius x prior_fault_rate x detection_severity
cost  = check_cost_units x stream_volume x runs_per_month(cadence)
```

and keeps the **cheapest cadence whose value still clears its cost**, dropping the
check otherwise. Two domain rules do real work:

- The expensive **tail-percentile check is scheduled only on streams that feed a
  tail-sensitive consumer.** A p99 check on a stream nobody reads for latency is
  pure waste. (See the four `skip` lines in the demo.)
- Cheap checks (freshness) run frequently on high-blast streams; expensive checks
  drop to coarser cadence as blast radius falls.

Sample of the decision log:

```
RUN  billing_rollup_daily   completeness_conditional  15min  $  942/mo | blast 9 -> 15min (value 4,050 >= cost 942)
RUN  edge_latency_15m       tail_percentiles          daily  $   98/mo | blast 5, tail-sensitive -> daily (value 1,620 >= cost 98)
skip session_events_log     tail_percentiles          --             | skip p99: no tail-sensitive downstream (blast 5)
skip support_tickets_hourly tail_percentiles          --             | skip p99: no tail-sensitive downstream (blast 1)
```

---

## The verdict (not a binary alert)

Output is a **trust ratio** per consumer: of the severity-weighted checks
protecting the streams it reads, how many held — plus blast radius and an estimated
clear-by time. *Soft signals propose; the count decides.* The verdict is
deterministic and auditable by construction.

```
revenue_dashboard   trust= 73% blast= 5  DEGRADED - usable with caution, clear-by ~90m
   x session_events_log:completeness_conditional (segment(s) dark: west)
sla_alerting        trust= 78% blast= 5  DEGRADED - usable with caution, clear-by ~120m
   x edge_latency_15m:tail_percentiles (p99=188ms | mean=46 p50=41 look fine)
exec_weekly_report  trust=100% blast= 4  TRUSTED - all protecting checks held
```

---

## Run it

```bash
pip install -r requirements.txt
python -m src.demo
```

No real data, no credentials, no external services. The synthetic generator plants
the faults; the detectors and triage engine find the ones worth finding.

## Layout

```
src/
  streams.py   multi-grain telemetry generator + planted faults (ground truth)
  checks.py    detectors: freshness, global completeness, conditional MNAR, tail percentiles
  lineage.py   dependency graph + blast-radius computation
  triage.py    cost vs blast-radius -> what to check, where, how often  (the headline)
  verdict.py   per-consumer trust ratio + blast radius + clear-by time
  demo.py      end-to-end story in five acts
```

## Design stance

- **Triaged, not exhaustive.** QA is not free; spend it where blast radius earns it.
- **Conditional, not aggregate.** The dangerous faults hide in the slices and the tails.
- **Deterministic verdicts.** A count of falsifiable checks, not a model grading itself.
- **Lineage-driven.** What to check, and how hard, is derived from what's downstream —
  not guessed, and not discovered by waiting for the scream.

---

*This is a clean-room reference implementation on synthetic data, built to make the
design legible. It generalizes the approach I took in production to replace
standard-deviation alerting with lineage-driven, cost-bounded data-contract
validation.*
