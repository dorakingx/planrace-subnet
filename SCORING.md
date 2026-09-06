# Scoring v2

PlanRace v2 ranks only artifacts that pass admission and produce exact result
equality across the validator's multiple unrevealed databases and parameter
sets. A wrong result, malformed bundle, policy violation, or excessive timeout
rate receives zero. If the reference query or benchmark worker fails, the
benchmark is invalid and weights are not updated from it.

The historical `planrace/1` absolute score remains in `planrace/scoring.py` only
to replay the v1 local-chain evidence. New mechanism work uses
`planrace/scoring_v2.py`.

## Same-worker relative measurement

The validator measures the known-correct baseline and candidate in the same
disposable worker. Trials use deterministic balanced ABBA interleaving of
`baseline-first` / `candidate-first` order. Mixed workers and unbalanced order
arms are invalid.
For each paired trial and reuse horizon `h ∈ {1, 10, 100, 1000}`:

```text
B_h = baseline_cold_ms + (h - 1) × baseline_warm_ms
C_h = (setup_ms + candidate_cold_ms + (h - 1) × candidate_warm_ms)
      × (1 + artifact_bytes / database_bytes × 0.10)
relative_log_speedup_h = log2(B_h / C_h)
```

The score uses a 10% winsorized center and a MAD-based lower confidence bound
for each horizon. The lower-bound speedup becomes fractional savings, never a
positive reward for a baseline-equivalent or slower artifact. Precommitted
horizon masses are 15%, 25%, 30%, and 30%. Candidate timeout frequency applies
a squared reliability penalty; a rate above 20% receives zero.

This construction includes cold time, warm time, setup cost, storage cost, and
timeouts while cancelling common hardware scale. It never trusts miner-reported
timings.

## Multi-epoch aggregation

Each miner needs at least 12 tasks, every required workload family, at least 75%
availability, and at least 95% compliance. Family scores receive fixed equal
mass so a validator cannot silently inflate a miner by over-sampling its best
family. The aggregate is a winsorized family center minus a MAD uncertainty
penalty, then multiplied by observed availability and compliance.

For each committed task, artifacts sharing a canonical executable-strategy
digest are evaluated once. Every duplicate identity receives the same
validator-owned evidence digest, and that task reward is divided across the
duplicate group. Multi-epoch aggregation therefore starts from fixed group
mass rather than identity count. At allocation time, full portfolios with the
same observed hidden-fixture query-plan behavior are grouped before the
concentration cap and divided back in proportion to their already-split
rewards. Byte-distinct near copies therefore cannot create reward, satisfy
diversity, or bypass the cap.

Final observed-behavior weights have a 25% cap. The production-oriented default
requires five distinct positive strategies. The published localnet integration
run explicitly binds a four-group threshold—the mathematical minimum compatible
with the cap—to exercise a complete chain write with four useful strategies; it
is not a claim that this is the final production governance setting. If all
candidates fail, diversity is insufficient, or the cap cannot be met, the
validator emits a no-new-update decision instead of fabricating a winner. This
does not erase a previously stored chain vector.

Every allocation reports strategy-level Gini, HHI, top-one share, and effective
strategy count.
Rank stability is measured with Kendall tau-b.

## Implementation boundary

`score_benchmark` consumes validator-owned measurements; it does not execute SQL
or weaken the sandbox. Production flow is
`signed response → evaluate-once cohort → aggregate_network → allocate_weights`.
Result canonicalization, hidden holdout construction, and sandbox enforcement
are protocol gates upstream of this mechanism. See `MECHANISM_SIMULATION.md`
for deterministic adversarial evidence and its stated limits.
