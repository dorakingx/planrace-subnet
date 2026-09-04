# PlanRace

**The competitive market for verified query plans.**

[Live evidence dashboard](https://planrace-subnet.vercel.app) ·
[GitHub](https://github.com/dorakingx/planrace-subnet)

PlanRace is a Bittensor subnet prototype where miners return faster SQL rewrites
and bounded index plans. Validators first require exact result equality on
unrevealed generated test databases; only correct artifacts compete on robust,
baseline-relative cold/warm latency, storage, and amortized setup cost.

```text
known-correct SQL + schema + commitment
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
      miner A  miner B  miner C
        │        │        │
        └────────┼────────┘
                 ▼
 unrevealed test rows → exact result hash gate → performance score → weights
```

## Why this is a subnet

Database workloads, engines, distributions, and releases keep changing. Independent miners can compete with rules, program synthesis, learned optimizers, and engine-specific expertise. Verification is cheaper than open-ended optimization: validators replay bounded artifacts, reject exact-result mismatches on test fixtures, and publish evidence that buyers can reproduce.

PlanRace does **not** translate natural language to SQL and does not sell query answers. Its digital commodity is a reusable, executable optimization artifact for an already-correct query.

## Working proof

Protocol v2 includes 18 simulation profiles across honest, noisy, timeout,
malformed, wrong-result, constant-answer, copycat/Sybil, validator-order, timing,
and all-fail scenarios. A committed 512-replication run preserves raw rows and a
source/lock/artifact hash manifest under
[`results/mechanism-v2/`](results/mechanism-v2/). It
recorded zero accepted injected false claims, zero gaming weight, fail-safe
no-update in every all-fail replication, and no material allocation gain from
duplicating a strategy.

The official local Subtensor protocol v2 run uses three test validator
identities under one operator, ten heterogeneous miners, 30 epochs, signed
requests and responses, multiple hidden fixtures, disposable Docker evaluation,
and an actual mechanism-derived weight write/readback. The verified run contains
300 authenticated requests, 270 signed responses, five capped strategy
allocations, and finalized extrinsic `9062-0002`; follow [STATUS.md](STATUS.md)
and [LOCALNET_V2.md](LOCALNET_V2.md).

```bash
make bootstrap
make sync
make verify
make demo
```

Or without Make:

The bootstrap installs the security-fixed, pinned `uv==0.12.7` inside `.bootstrap`; it does not modify the system Python environment.

## Protocol v2

1. A validator creates independent CSPRNG seed and salt material, then publishes
   a commitment with the pinned engine/sandbox, schema, known-correct SQL,
   public workload distribution, strict artifact budget, and deadline.
2. Receiver-bound Bittensor-authenticated requests reach each miner. The miner
   returns a bounded structured bundle in a domain-separated sr25519-signed
   response with nonce and expiry protection.
3. After the deadline the validator seals submissions, reveals the commitment,
   and deterministically creates multiple hidden fixtures across a closed family
   schedule.
4. Reference and candidate execute only in disposable, network-disabled,
   resource-capped workers. Canonical result hashes must match on every fixture.
5. Exact and compliant strategies compete against the same-fixture baseline on
   cold/warm latency, setup/storage, and multiple reuse horizons.
6. Conservative multi-epoch aggregation enforces availability, correctness,
   compliance, family coverage, duplicate splitting, fail-safe no-update, and a
   per-strategy weight cap before the chain update.

See [PROTOCOL_V2.md](PROTOCOL_V2.md),
[BENCHMARK_POLICY.md](BENCHMARK_POLICY.md), [SCORING.md](SCORING.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [THREAT_MODEL.md](THREAT_MODEL.md), and
[EVIDENCE_INDEX.md](EVIDENCE_INDEX.md).

Future-block entropy mixing is not implemented. Current task material is
independently unpredictable from its public commitment, but that limitation is
kept explicit.

## Historical protocol v1

1. A validator publishes `QueryTask`: pinned engine, schema, known-correct SQL, task-generator version, seed commitment, limits, and repetitions.
2. A miner returns `OptimizationArtifact`: candidate SQL plus at most two admitted `CREATE INDEX` statements.
3. After the deadline, the validator reveals the task seed and builds the generated test database deterministically.
4. Reference and candidate results are canonicalized and SHA-256 hashed. Any mismatch receives zero.
5. Correct artifacts are scored by repeated warm latency, plan complexity, and amortized setup cost.
6. Epoch scores are aggregated into non-negative miner weights for Bittensor consensus.

See [MECHANISM.md](MECHANISM.md) and [PROTOCOL.md](PROTOCOL.md). Protocol v1
encoded a deterministic fixture seed in its task ID and did not sign miner
responses; it is preserved for provenance and is not the current security claim.

## Bittensor localnet proof

The current implementation has also completed a request-authenticated end-to-end epoch on an
official local Subtensor image. Two registered miners served receiver-bound HTTP
requests; protocol v1 responses were not signed. Exact-result verification scored the honest miner above zero and
hard-gated the gaming miner to zero; the validator then wrote the resulting
weight to netuid 2. See [LOCALNET.md](LOCALNET.md) and the
[machine-readable run](results/localnet-epoch-8.json).

## Current status

Implemented now: opaque commit/reveal, strict v2 wire types, bidirectional
signatures and replay controls, exact/canonical result semantics, disposable
Docker sandboxing, robust baseline-relative scoring, multi-epoch duplicate-aware
weights, adversarial mechanism simulation, and a verified 30-epoch localnet v2
weight submission/readback.

Not yet claimed: Bittensor testnet registration/weights, independently operated
validators, PostgreSQL/DuckDB or private customer-data adapters, a clean v2
evidence-dashboard deployment, the real-testnet demo, or HackQuest submission.

Progress is tracked in [STATUS.md](STATUS.md). No mainnet or paid service is authorized.

## Safety boundary

- Network targets are limited to localnet and testnet in the planned adapter.
- Candidate SQL is read-only and setup artifacts are bounded index DDL.
- Generated data avoids customer information.
- Candidate execution is confined to disposable, resource-capped workers; the
  current worker remains a generated SQLite mechanism proof, not production
  database isolation certification.
- No wallet seed, token, or secret belongs in this repository.

## Selection provenance

PlanRace was selected after a zero-base review of 42 commodity-first ideas, blind official-criteria scoring, weight sensitivity, an adversarial top-eight review, and three isolated working spikes. QECForge's existing code and sunk cost were excluded. See [IDEA_RESELECTION.md](IDEA_RESELECTION.md) and [PIVOT_DECISION.md](PIVOT_DECISION.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
