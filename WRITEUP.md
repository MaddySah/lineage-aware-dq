# The Scream Test Is Not a Data Quality Strategy

*How I replaced standard-deviation alerting with lineage-driven, cost-bounded data
contract validation — and why "check everything" is the wrong answer.*

---

Most data quality fails in one of two ways, and both are expensive.

The first is the **scream test**. You ship the data, and the test is whether
someone downstream screams that their numbers are wrong. It costs nothing right up
until it costs everything: by the time the scream arrives, the bad data has already
flowed into a revenue dashboard, an exec report, an alerting system, and you're
doing forensics instead of prevention.

The second is the brute-force overcorrection: **check everything, everywhere, all
the time.** Every stream, every fifteen minutes, every expensive statistic. In a
real multi-grain telemetry environment — streams arriving at daily, hourly, 15-minute,
and log grain — that bill runs into tens of thousands of dollars a month and it
bottlenecks the very ingestion pipeline it's supposed to protect.

I spent a while living between those two failures, and the system I built to escape
them rests on one idea: **data quality is not free, so data quality must be
triaged.**

## Importance is inherited, not intrinsic

A stream doesn't matter on its own. It matters because of what depends on it. A
log stream feeding a revenue dashboard and a regulatory report is not the same risk
as a log stream feeding an internal nice-to-have view, even if the two streams look
identical.

So the first move is to stop treating streams as equally important and start
deriving each one's **blast radius** from the lineage: the criticality-weighted
count of downstream consumers it reaches. That single number reorders everything.
It tells you where a fault would actually hurt, which is the only sane basis for
deciding where to spend a finite QA budget.

## The checks that matter are the ones aggregates hide

Here's the part that makes triage worth doing well rather than crudely. The cheap,
shallow checks — overall row count, simple freshness — are exactly the ones that
**lie to you**, because the dangerous faults don't show up in aggregate.

Two examples, both of which I plant and catch in the reference implementation:

**A segment-level gap that stays invisible.** One segment of a stream silently
stops reporting. The global completeness check stays green — overall volume is
still 84% of expected, comfortably above any reasonable floor — while an entire
segment is dark. The only thing that finds it is a *conditional* check that
validates completeness **per segment**. Missingness is rarely random, and the
shape of what's missing is itself the signal. Aggregate checks are structurally
blind to it.

**A tail that drifts while the average holds.** p99 latency degrades badly while
the mean and the median don't move at all. Every average-based monitor reports
healthy. Aggregation waters down precisely the detail you care about, so the tail
percentiles — p50, p90, p95, p99 — have to be preserved sharply. And because
computing percentiles over raw samples is expensive, you cannot afford to run them
everywhere. They have to be **targeted** onto the streams where a tail actually
matters to someone downstream.

That last constraint is the whole game. The expensive check is also the most
revealing one, so the system's intelligence is in deciding *where it's worth it*.

## The engine: value versus cost, per check

For every combination of stream and check, the triage engine weighs two numbers:

- **Value** = blast radius × how likely this check is to find something × how bad
  it is to miss.
- **Cost** = the check's compute weight × the stream's data volume × how often
  you'd run it.

It keeps the cheapest cadence whose value still clears its cost, and drops the
check otherwise. Two rules encode the domain judgment: the expensive
tail-percentile check is scheduled **only** on streams that feed a tail-sensitive
consumer, and cheap checks run often on high-blast streams while expensive checks
fall back to coarser cadence as blast radius drops.

In the reference run, this takes a brute-force baseline of **$68,000/month** down to
**under $10,000/month — about 85% less spend — while still catching every silent,
high-blast-radius fault the cheap aggregate monitor reported as green.** That is the
entire point: not cheaper QA, but QA aimed correctly.

## The output is a verdict, not an alarm

A standard-deviation alert tells you "something moved." That's nearly useless to the
person holding the pager at 2am. What they need is: *can I trust this, by how much,
which downstream reports are affected, and until when?*

So the output is a **trust ratio** per consumer — of the severity-weighted checks
protecting the streams it reads, how many held — paired with the blast radius and an
estimated clear-by time. A revenue dashboard reading a stream with a dark segment
comes back "DEGRADED, 73% trust, clear-by ~90m" with the specific failed check
named. An exec report whose streams all passed comes back "TRUSTED, 100%."

Crucially, that verdict is **deterministic**. It's a count over falsifiable checks,
not a model grading its own homework. Soft signals can propose what to look at; the
count decides what's true. In a governance or audit context that distinction is the
difference between a number you can defend and a number you can only hope is right.

## Why this generalizes

The shape here isn't specific to telemetry. It's a pattern I keep coming back to:
**derive what to check from the system's own structure, generate falsifiable checks
for exactly the blind spots, weight the effort by blast radius, and reduce the
verdict to a count.** It's the same instinct whether the target is a data pipeline,
a model's outputs, or a system's conformance to its own documented design.

The brute-force version of any of these is easy and wrong. The scream-test version
is cheap and dangerous. The useful version is the one that knows the difference
between what's worth checking and what isn't — and can show you the arithmetic
behind every call.

---

*A runnable, clean-room reference implementation on synthetic data accompanies this
piece. It plants the faults described above and catches them, end to end, in a
single command. The approach generalizes work I did in production replacing
standard-deviation alerting with lineage-driven data contract validation.*
