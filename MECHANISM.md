# Incentive Mechanism v2

## Commodity and validity

The v2 commodity is a versioned, canonical optimization bundle admitted by the
track policy. The validator—not the miner—executes it in isolation. A candidate
is valid only when it produces exact result equality against the known-correct
query across multiple unrevealed databases and parameter sets. Incorrect,
malformed, non-compliant, late, replayed, or over-budget submissions receive
zero.

This does not claim universal semantic equivalence. It is finite, replayable
evidence over a precommitted hidden holdout and pinned engine.

## Lifecycle

1. **Commit:** bind the opaque task, validator, engine/generator/policy digests,
   hidden fixture root, deadline, and independent secret seed/salt.
2. **Compete:** authenticated miners return signed, receiver-bound bundles
   without access to holdout fixtures.
3. **Close:** seal accepted submissions at the deadline; reject late or replayed
   responses.
4. **Reveal and audit:** reveal after close so peers can regenerate the logical
   fixtures, verify the commitment, and check the exact generator source at the
   run's recorded Git commit.
5. **Gate:** enforce admission, isolation, resource limits, and exact result
   equality. Any gate failure is zero.
6. **Benchmark:** interleave candidate and reference measurements on the same
   worker across cold/warm runs and four reuse horizons.
7. **Aggregate:** apply fixed family quotas, robust centers, uncertainty,
   availability, compliance, and canonical duplicate grouping.
8. **Allocate:** cap concentration, publish metrics, and produce either a
   non-negative vector or an explicit no-new-update decision.

## Score and weight policy

The complete formula and defaults are in `SCORING.md` and executable in
`planrace/scoring_v2.py`. Important invariants are:

- absolute worker speed cannot create advantage because every timing is paired
  with its baseline on that worker;
- setup and storage can make a candidate lose at horizon 1 yet win at horizon
  1000, and all four precommitted horizons retain weight;
- wrong/constant results and malformed bundles cannot trade correctness for
  speed;
- timing outliers influence a winsorized center and a downside confidence bound;
- one strategy digest receives one reward pool even when submitted by multiple
  identities;
- fewer than five distinct positive behaviors, all-fail outcomes, or an
  unsatisfiable 25% cap produce no new update. A prior on-chain vector is not
  cleared automatically and must be monitored through `last_update` and the
  activity cutoff.

## Gaming and validator analysis

| Attack | v2 response | Remaining risk |
|---|---|---|
| Constant or fast wrong output | Exact hidden-holdout gate → zero | Holdout/generator leakage |
| Claim fabricated timing | Validator-owned same-worker timing | Compromised validator worker |
| Faster/slower validator hardware | Baseline-relative paired ratios | Architecture-specific query-plan changes |
| First/second-run cache bias | Balanced randomized interleaving | Higher-order thermal/IO drift |
| One extreme timing sample | Winsorized center + MAD lower bound | Coordinated nonstationary noise |
| Optimize only warm cache | Separate cold/warm metrics and four horizons | Chosen horizon masses are governance policy |
| Index everything | Setup + storage overhead | Storage proxy may not equal buyer cost |
| Duplicate/Sybil identities | Canonical digest group splits fixed reward | Novel-looking collusive artifacts |
| Validator curriculum skew | Fixed workload-family mass | Biased generator inside a family |
| Every candidate fails | Explicit no-update | Liveness until honest candidates return |

## Evidence and limitations

`results/mechanism-v2/` contains 512 deterministic multi-epoch replications, 18
miner profiles, eight validator conditions, CSV/JSON outputs, environment/lock
hashes, and a source/seed manifest. See `MECHANISM_SIMULATION.md`.

Synthetic simulation validates implementation invariants and exposes policy
sensitivity; it is not testnet evidence, proof of economic equilibrium, or proof
against arbitrary collusion. Historical v1 evidence remains replayable and is
not relabelled as v2.
