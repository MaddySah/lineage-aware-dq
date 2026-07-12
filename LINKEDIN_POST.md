# LinkedIn Post — draft

---

We had a smoke detector that only went off after the house had already burned down.

In data quality there's a thing I call the scream test: you ship the data, and the "test" is whether someone downstream screams that their numbers are wrong. By the time they scream, the bad data is already in the revenue dashboard. You're not preventing anything — you're doing forensics.

The obvious fix is to check everything, every 15 minutes. But in a multi-grain telemetry setup that bill hits ~$68k/month and chokes your ingestion. So you're stuck between cheap-and-dangerous and thorough-and-broke.

I kept landing on the same idea to escape that: **data quality isn't free, so it has to be triaged.** A stream doesn't matter on its own — it matters because of what depends on it. So you walk the lineage, compute each stream's blast radius, and spend your QA budget only where the blast radius earns it.

The faults worth catching are the ones aggregates hide:
→ a segment goes dark while overall volume still looks 84% healthy (only a per-segment check finds it)
→ p99 latency degrades while the mean and median don't move at all (only a targeted percentile check finds it)

And percentiles are expensive, so you run them only where a tail actually matters downstream.

In the reference build, this takes the brute-force $68k/month plan down to under $10k — about 85% less — while still catching every silent, high-blast fault the cheap monitor reported as green. And the output isn't "something moved." It's a trust ratio: how much to trust this report, which checks failed, and when it'll clear.

I wrote it up and put a runnable version on GitHub — synthetic data, plants the faults, catches them in one command. Links in comments.

The honest origin story: I didn't set out to build "lineage-driven data contract validation." I got annoyed by manual QA effort and built a thing that killed the annoyance. It turned out to have a name afterward. That's usually how it goes.

#DataQuality #DataEngineering #MLOps #ResponsibleAI #DataObservability

---
