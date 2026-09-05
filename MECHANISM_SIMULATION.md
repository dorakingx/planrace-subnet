# Mechanism v2 Simulation

## Scope

This is deterministic synthetic mechanism evidence, not local-chain or testnet
evidence. It asks whether the implemented v2 scorer fails closed, stays
baseline-relative under hardware changes, resists known shortcut profiles, and
avoids concentrated or Sybil-amplified allocation under the simulated policy.

The committed run uses:

- 512 replications × 24 epochs;
- 20 miner identities representing 19 exact executable strategies and 18
  observed-behavior groups (12 honest/search profiles, four gaming profiles,
  two exact-copy identities, and two byte-distinct near-copy identities);
- 10 balanced paired trials per available unique strategy/task evaluation, or
  2,019,140 measured baseline/candidate trial pairs in total;
- four workload families and reuse horizons 1/10/100/1000;
- eight validator conditions: honest, fast hardware, slow hardware, order bias,
  timing outliers, candidate-only measurement bias, an injected false-correctness claim, and
  all-fail.

The simulation seed is disclosed in the manifest. Python, SQLite, platform,
dependency-lock, source-file, config, and output hashes are recorded alongside
the results.

## Results

| Metric | Committed result |
|---|---:|
| Replications | 512 |
| Unique strategy/task evaluations | 233,472 |
| Duplicate-evaluation cache hits | 12,288 |
| Incorrect or non-compliant strategy evaluations | 42,609 |
| False acceptances / false-acceptance rate | 0 / 0.000000 |
| Injected / accepted false-correctness claims | 6,089 / 0 |
| Honest winner rate (non-all-fail conditions) | 1.0000 |
| Gaming weight | 0.0000 |
| All-fail no-new-update rate | 1.0000 |
| Mean / maximum top-one behavior share | 0.1256 / 0.2500 |
| Mean behavior Gini | 0.1606 |
| Mean behavior HHI | 0.1006 |
| Mean rank stability vs expected profiles, Kendall tau-b | 0.5635 |
| Fast-vs-slow paired ranking tau-b (64 paired cohorts) | 1.0000 |
| Mean cross-validator allocation TV (1,344 actual pairs) | 0.1427 |
| Maximum exact/near-copy behavior allocation gain | 0.0 |

All 64 all-fail replications produced no new update. Each of the other seven
conditions produced a valid allocation in all 64 replications. The timing
outlier condition had mean tau-b 0.5456; its false-acceptance rate and gaming
weight remained zero.

Duplicate and near-copy identities intentionally receive some weight because
they submit correct optimization profiles. Each exact `(task commitment,
executable digest)` is evaluated once and split. At allocation, byte-distinct
portfolios with the same observed behavior neither add group mass nor satisfy
diversity. For every active replication, the simulation reruns aggregation
without the extra identities and compares the behavior group's final mass.
Across 448 comparisons, the maximum computed gain was exactly `0.0`. This is
not a claim that behavior grouping solves general Sybil identity or collusion.

## Profiles and attacks

Honest profiles span covering/partial/aggregate index advisors, first-execution and warm
specialists, low-storage and high-setup candidates, noisy search, and a
timeout-prone candidate. Gaming profiles return constant, fast-wrong,
fixture-memorized, or malformed artifacts. The false-accept scenario sets
`miner_claimed_correct=true` on measured-wrong submissions. The claim is not an
input to `score_benchmark`; only validator-owned measured correctness is used.
All 6,089 injected false claims were rejected.

Hardware scale multiplies reference, candidate, and setup time together. Fast
and slow validators share the same random cohort and are compared directly;
their 64 paired rankings had mean tau-b 1.0000. Cross-validator disagreement is
the pairwise total-variation distance between actual strategy allocations from
the same cohort, not distance from a theoretical distribution. No-update rows
are excluded from pair metrics and retained as explicit nulls in the evidence.
Order-bias alternates which side pays first/second-run effects. Timing-outlier
trials inject 4×–12× delays. Candidate-measurement bias changes candidate time
without scaling the baseline or setup, directly exercising validator-side
measurement distortion.

## Reproduce

```bash
.bootstrap/bin/uv run python scripts/run_mechanism_v2.py
.bootstrap/bin/uv run python scripts/verify_mechanism_v2.py --require-clean-source
```

The publication command rejects fewer than 500 replications. It rewrites:

- `results/mechanism-v2/simulation.json` — configuration, policies, profiles,
  every replication, and summary;
- `results/mechanism-v2/summary.json` — review-sized metrics;
- `results/mechanism-v2/replications.csv` — one row per replication;
- `results/mechanism-v2/MECHANISM_SIMULATION.json` and
  `MECHANISM_SIMULATION.csv` — publication-name byte-identical aliases of the
  full JSON and replication CSV;
- `results/mechanism-v2/profile-rewards.csv` — reward/weight/gate outcomes;
- `results/mechanism-v2/manifest.json` — seed, environment, lock, source, and
  artifact hashes.

Tests may use smaller runs through `SimulationConfig`; the publication CLI
enforces both the ≥500-replication and ≥24-epoch evidence floors.

## Interpretation limits

The run supports implementation claims about these fixtures and attacks. It does
not establish live validator agreement, network latency behavior, economic
equilibrium, arbitrary-query correctness, universal semantic equivalence, or
testnet performance. Those claims require the separate v2 local-chain and
testnet evidence gates.
