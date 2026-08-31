# PlanRace

**The competitive market for verified query plans.**

[Live evidence dashboard](https://planrace-verified-sql.doraking.chatgpt.site) ·
[GitHub](https://github.com/dorakingx/planrace-subnet)

PlanRace is a Bittensor subnet prototype where miners return faster SQL rewrites and bounded index plans. Validators first require exact result equivalence on hidden generated databases; only correct artifacts compete on robust latency, plan cost, and amortized setup cost.

```text
known-correct SQL + schema + commitment
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
      miner A  miner B  miner C
        │        │        │
        └────────┼────────┘
                 ▼
 hidden rows → exact result hash gate → performance score → weights
```

## Why this is a subnet

Database workloads, engines, distributions, and releases keep changing. Independent miners can compete with rules, program synthesis, learned optimizers, and engine-specific expertise. Verification is cheaper than open-ended optimization: validators replay bounded artifacts, reject semantic drift exactly, and publish evidence that buyers can reproduce.

PlanRace does **not** translate natural language to SQL and does not sell query answers. Its digital commodity is a reusable, executable optimization artifact for an already-correct query.

## Working proof

The repository includes three miner profiles and a multi-epoch simulator:

- `honest-indexed` returns the exact query with selective partial indexes;
- `baseline` returns the correct query unchanged;
- `gaming-fast-wrong` widens a filter to appear productive but changes results.

The validator generates hidden skewed datasets from committed seeds. Wrong results score zero before latency matters.

```bash
make bootstrap
make sync
make verify
make demo
```

Or without Make:

The bootstrap installs the security-fixed, pinned `uv==0.12.7` inside `.bootstrap`; it does not modify the system Python environment.

## Protocol v1

1. A validator publishes `QueryTask`: pinned engine, schema, known-correct SQL, task-generator version, seed commitment, limits, and repetitions.
2. A miner returns `OptimizationArtifact`: candidate SQL plus at most two admitted `CREATE INDEX` statements.
3. After the deadline, the validator reveals the task seed and builds the hidden database deterministically.
4. Reference and candidate results are canonicalized and SHA-256 hashed. Any mismatch receives zero.
5. Correct artifacts are scored by repeated warm latency, plan complexity, and amortized setup cost.
6. Epoch scores are aggregated into non-negative miner weights for Bittensor consensus.

See [MECHANISM.md](MECHANISM.md), [PROTOCOL.md](PROTOCOL.md), [SCORING.md](SCORING.md),
[ARCHITECTURE.md](ARCHITECTURE.md), and [THREAT_MODEL.md](THREAT_MODEL.md).

## Bittensor localnet proof

The current implementation has also completed a signed, end-to-end epoch on an
official local Subtensor image. Two registered miners served receiver-bound HTTP
responses; exact-result verification scored the honest miner above zero and
hard-gated the gaming miner to zero; the validator then wrote the resulting
weight to netuid 2. See [LOCALNET.md](LOCALNET.md) and the
[machine-readable run](results/localnet-epoch-8.json).

## Current status

Implemented now:

- strict immutable wire models;
- deterministic commit/reveal workload generator;
- SQL and index-artifact admission rules;
- SQLite query deadline;
- exact result-hash gate;
- repeated timing, setup amortization, and plan-cost scoring;
- honest, low-quality, and gaming miners;
- multi-epoch simulation and tests.
- Bittensor v11 receiver-bound signed miner HTTP;
- validator dispatch and deterministic weight planning;
- official Subtensor localnet registration, Axon publication, and weight evidence.

Not yet claimed:

- Bittensor testnet registration or on-chain weight evidence;
- independent-validator timing calibration;
- production sandbox isolation;
- DuckDB/PostgreSQL tracks;
- public dashboard/video or final HackQuest submission.

Progress is tracked in [STATUS.md](STATUS.md). No mainnet or paid service is authorized.

## Safety boundary

- Network targets are limited to localnet and testnet in the planned adapter.
- Candidate SQL is read-only and setup artifacts are bounded index DDL.
- Generated data avoids customer information.
- Production execution must move from an in-process SQLite prototype to disposable, resource-capped workers.
- No wallet seed, token, or secret belongs in this repository.

## Selection provenance

PlanRace was selected after a zero-base review of 42 commodity-first ideas, blind official-criteria scoring, weight sensitivity, an adversarial top-eight review, and three isolated working spikes. QECForge's existing code and sunk cost were excluded. See [IDEA_RESELECTION.md](IDEA_RESELECTION.md) and [PIVOT_DECISION.md](PIVOT_DECISION.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
