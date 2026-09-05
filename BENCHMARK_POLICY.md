# Benchmark Policy v2

The benchmark policy is committed before miner submission. The worker
recomputes its digest and rejects any mismatch; a validator cannot change
horizons, trials, timeout tolerance, storage penalty, result semantics, or
sandbox limits after seeing an artifact.

## Workload

- Engine: CPython's pinned SQLite 3.46.1 worker image.
- Public input: one separately seeded training fixture, query text, schema,
  parameter ranges, coarse row/selectivity ranges, and artifact grammar.
- Private input: eight independently derived profiles covering zero rows,
  small data, skew, NULL-heavy data, duplicates, correlation, boundaries, and
  a larger aggregate.
- Query families: paid revenue, customer threshold, bounded range, regional
  aggregation, nullable coupon, and intentional zero-result behavior.
- Trials: six ABBA-balanced baseline/candidate pairs using fresh database
  connections; every pair records first-query and immediate-repeat warm
  measurements. “Cold” field names mean fresh-connection first query, not a
  flushed operating-system page cache.

## Isolation envelope

The default container has no network, a read-only root, a read-only fixture
mount, a no-exec temporary work area, no Linux capabilities, no-new-privileges,
one CPU, 256 MiB memory, equal memory/swap limits, 16 PIDs, a non-root UID, and
file-descriptor/CPU limits. Each query has a 750 ms SQLite progress deadline.
The validator bounds worker input/output and the whole process wall clock.

Localnet cohort batching amortizes container startup while retaining the same
container boundary. It accepts at most 64 committed requests, uses bounded
4 MiB envelopes, 256 MiB memory, and an absolute 900-second maximum. Each item
still gets its own copied database, exact-result oracle, query deadline,
artifact validation, and evidence binding. A batch crash zeros that batch and
does not stop the validator.

## Reward

For reuse horizon `h`, the candidate includes one-time setup cost and storage
penalty while the reference does not:

```text
B_h = baseline_cold + (h - 1) × baseline_warm
C_h = (setup + candidate_cold + (h - 1) × candidate_warm)
      × (1 + artifact_bytes / database_bytes × 0.10)
```

The validator takes paired log-speedups, a finite-sample 10% winsorized center,
and a MAD-based lower confidence bound. The default six-trial policy clips at
least one observation from each tail, preventing one extreme trial from
dominating even though `floor(6 × 10%)` is zero. Positive lower-bound savings receive horizon
weights 15%, 25%, 30%, and 30% for `h = 1, 10, 100, 1000`. Candidate timeout
frequency receives a squared reliability penalty; more than 20% is zero.

Eight holdout rewards combine as 60% lower-quartile mean and 40% geometric
mean. Therefore a strategy must work beyond a single favorable data shape.
Empty or unused indexes receive zero regardless of timing noise.

## Network aggregation

The schedule is closed and binds epoch, family, task ID, and commitment. Missing
observations are filled as zero; unscheduled or inconsistent evidence is
rejected. Equal-mass family scores prevent curriculum padding. Availability,
compliance, correctness, minimum task count, and worst-family gates precede
allocation. Identical task strategies are evaluated once and split. Full
portfolios are grouped by their observed hidden-fixture query-plan behavior, so
byte-distinct near copies neither satisfy diversity nor add group mass. Each
task admits at most 64 unique executable strategies before worker dispatch.

Defaults require five positive behavior groups and cap each group at 25%.
Failure to satisfy correctness, diversity, or cap feasibility returns an
explicit no-new-update decision. On a live chain this does not erase a prior
vector: old weights can remain effective until replaced or aged out by chain
policy, so operators monitor `last_update` and the subnet activity cutoff.
