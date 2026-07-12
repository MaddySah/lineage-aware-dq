"""
End-to-end demo. Run:  python -m src.demo   (from repo root)

Tells the story in five acts:
  1. The streams and who depends on them (lineage + blast radius)
  2. The brute-force baseline cost ('check everything every 15 min')
  3. Naive aggregate checks run -> they MISS the MNAR and tail faults (false green)
  4. The triage engine decides what to actually check, and why
  5. Targeted checks run -> they CATCH the faults, at a fraction of the cost,
     and emit a per-consumer trust verdict
"""

from __future__ import annotations
from .streams import build_streams, generate_window
from .lineage import default_consumers, wire_lineage, blast_radius, feeds_tail_sensitive
from .checks import (check_freshness, check_completeness_global,
                     check_completeness_conditional, check_tail_percentiles)
from .triage import (triage, baseline_everything_cost, plan_cost, CHECK_COST_UNITS)
from .verdict import consumer_verdict

BAR = "=" * 74
SLA = {"15min": 30, "hourly": 90, "daily": 1500, "log": 30}


def hr(title):
    print("\n" + BAR + "\n" + title + "\n" + BAR)


def main():
    streams = build_streams()
    consumers = default_consumers()
    wire_lineage(streams, consumers)

    # Calibrate $/unit so the brute-force baseline lands at $68,000 - the real
    # number that motivated this system.
    raw_baseline = baseline_everything_cost(streams, dollars_per_unit=1.0)
    DOLLARS_PER_UNIT = 68000.0 / raw_baseline
    baseline = baseline_everything_cost(streams, DOLLARS_PER_UNIT)

    hr("ACT 1  -  STREAMS & BLAST RADIUS  (importance is inherited, not intrinsic)")
    for s in streams:
        br = blast_radius(s, consumers)
        tail = " [feeds tail-sensitive consumer]" if feeds_tail_sensitive(s, consumers) else ""
        print(f"  {s.id:<24} grain={s.grain:<6} blast={br:>4.0f}  -> {', '.join(s.consumers)}{tail}")

    hr("ACT 2  -  BRUTE-FORCE BASELINE  ('check everything, every 15 min')")
    print(f"  Every check x every stream x 2880 runs/month")
    print(f"  Monthly cost: ${baseline:,.0f}   <- the bill nobody wants to pay")

    hr("ACT 3  -  NAIVE AGGREGATE CHECKS  (cheap, and they LIE)")
    print("  Running only freshness + GLOBAL completeness on everything:\n")
    missed = []
    for s in streams:
        w = generate_window(s, faulted=True)
        f1 = check_freshness(w, SLA[s.grain])
        f2 = check_completeness_global(w)
        # what an aggregate-only monitor would conclude
        verdict = "OK" if (f1.passed and f2.passed) else "FLAGGED"
        print(f"  {s.id:<24} {verdict:<8} ({f2.reason})")
        # ground-truth faults that aggregate checks cannot see
        if s.planted.get("mnar_segment") and f2.passed:
            missed.append((s.id, "segment-level MNAR gap"))
        if s.planted.get("tail_drift"):
            missed.append((s.id, "p99 tail drift"))
    print("\n  >> Aggregate monitor says mostly GREEN. But it silently missed:")
    for sid, fault in missed:
        print(f"       - {sid}: {fault}")

    hr("ACT 4  -  TRIAGE ENGINE  (what to check, where, how often, WHY)")
    decisions = triage(streams, consumers, DOLLARS_PER_UNIT)
    on = [d for d in decisions if d.cadence != "off"]
    off = [d for d in decisions if d.cadence == "off"]
    for d in on:
        print(f"  RUN  {d.stream_id:<24} {d.check:<26} {d.cadence:<6} "
              f"${d.monthly_cost:>7,.0f}/mo  | {d.rationale}")
    print()
    for d in off:
        print(f"  skip {d.stream_id:<24} {d.check:<26} {'--':<6} {'':>9}  | {d.rationale}")
    triaged = plan_cost(decisions)
    print(f"\n  Triaged monthly cost: ${triaged:,.0f}   "
          f"(vs ${baseline:,.0f} baseline -> {1 - triaged/baseline:.0%} saved)")

    hr("ACT 5  -  TARGETED CHECKS RUN  (catch what aggregates hid) + VERDICT")
    # run exactly the scheduled checks, collect findings
    sched = {}
    for d in on:
        sched.setdefault(d.stream_id, set()).add(d.check)

    findings = []
    caught = []
    for s in streams:
        w = generate_window(s, faulted=True)
        for check in sched.get(s.id, set()):
            if check == "freshness":
                f = check_freshness(w, SLA[s.grain])
            elif check == "completeness_global":
                f = check_completeness_global(w)
            elif check == "completeness_conditional":
                f = check_completeness_conditional(w)
            elif check == "tail_percentiles":
                f = check_tail_percentiles(w)
            findings.append(f)
            if not f.passed:
                caught.append(f"{s.id}: {f.check} -> {f.reason}")

    print("  Faults CAUGHT by targeted checks:")
    for c in caught:
        print(f"     [CAUGHT] {c}")

    print("\n  Per-consumer trust verdict:\n")
    for c in consumers:
        v = consumer_verdict(c, findings)
        clear = f", clear-by ~{v.clear_by_minutes:.0f}m" if v.failed else ""
        print(f"  {c.id:<22} trust={v.trust:>5.0%} blast={v.blast:>3.0f}  {v.headline}{clear}")
        for fl in v.failed:
            print(f"        x {fl}")

    hr("BOTTOM LINE")
    print(f"  Same high-blast-radius faults caught. {1 - triaged/baseline:.0%} less spend.")
    print(f"  Aggregate-only monitoring missed {len(missed)} silent faults that")
    print(f"  targeted, lineage-aware checks caught - for ${triaged:,.0f}/mo, not ${baseline:,.0f}.")
    print(BAR)


if __name__ == "__main__":
    main()
