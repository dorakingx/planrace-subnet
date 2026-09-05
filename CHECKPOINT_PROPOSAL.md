# HackQuest checkpoint proposal

Status: **draft — independent review findings are being remediated before posting**.

## Project

**PlanRace — The competitive market for verified query plans.**

PlanRace is a Bittensor subnet prototype where miners compete to return bounded,
executable structured index plans for validator-owned, already-correct SQL.
Validators create a precommitted challenge, authenticate requests, verify
miner-signed responses, reveal multiple hidden generated fixtures after the
deadline, require exact result equality, and only then score robust performance
relative to the unmodified baseline.

## Problem and user

Database teams repeatedly tune the same important queries, but today they must
either trust a single vendor's recommendation or spend scarce engineer time
searching a large, engine-specific design space. An optimizer can propose an
index quickly; proving that it preserves results and improves a workload across
data shapes is the expensive part. PlanRace targets teams operating recurring
analytical or transactional SQL workloads and gives them a competitive market
for improvements whose claims are independently replayable.

## Why a subnet

Mining is open-ended: rules, learned search, cost models, and engine experts can
all produce a small structured candidate. Validation is bounded: execute the
validator-owned query, compare canonical results, and benchmark in a committed
sandbox policy. Bittensor turns that asymmetric problem into continuing
competition, where weights pay measured reusable value instead of a miner's
self-reported benchmark.

## Architecture

```text
buyer workload adapter (future)
  -> validator precommit + signed challenge
  -> competing miner IndexSpec bundles
  -> isolated exact-result gate + paired benchmark
  -> multi-family conservative aggregation
  -> behavior-group cap + Bittensor weights
  -> signed public evidence manifest
```

The v2 network commodity is deliberately narrow: a bounded `IndexSpec` bundle,
not arbitrary SQL, an answer, or a benchmark supplied by the miner.

## Scoring and incentives

For each reuse horizon `h`, validators compare the same-fixture baseline cost
`B_h` with candidate cost `C_h`, including one-time setup and storage penalty.
Six paired ABBA trials use a finite-sample winsorized log-speedup and a MAD
lower confidence bound. Eight hidden fixtures combine downside and geometric
performance; a closed family-balanced epoch schedule then gates availability,
compliance, correctness, minimum coverage, and worst-family performance.

Exact executable duplicates are evaluated once and split. Byte-distinct
strategies with the same observed hidden-fixture plans share one behavior group;
five positive groups are required and no group can receive more than 25%.
Failed gates create no new chain update and are never presented as cleared old
weights.

## Checkpoint progress

- Protocol v2 removes deterministic seed disclosure from public task IDs and
  uses independent OS-CSPRNG seeds and salts with post-deadline reveal.
- Requests are receiver-bound using Bittensor HTTP authentication; responses
  carry a miner sr25519 signature and replay window.
- Validator-owned SQL and miner-supplied structured indexes execute only inside disposable, resource-capped
  Docker workers; timeout, crash, oversize, and invalid-output failures become
  zero/unavailable observations rather than validator crashes.
- Scoring is exactness-first, baseline-relative, uncertainty-aware, multi-family,
  multi-horizon, multi-epoch, and duplicate-strategy aware.
- A seeded 512-replication adversarial simulation is committed under
  `results/mechanism-v2/`.
- Protocol v2 localnet evidence completed with three test validator identities
  under one operator, ten heterogeneous miners, 30 epochs, 300 authenticated
  requests, 270 signed responses, and a successful mechanism-derived weight
  extrinsic/readback on an official local Subtensor container. It is not
  testnet evidence.

## What judges can run

```bash
make bootstrap
make test
make audit-v2
.bootstrap/bin/uv run python scripts/verify_mechanism_v2.py --require-clean-source
```

The public dashboard reads the committed manifest rather than hand-entered
counters. The repository also contains raw epoch records, miner signatures,
commit/reveal material, source hashes, the mechanism simulator, and independent
auditors.

## Current limits and roadmap

The current execution track is SQLite on generated data. Private customer-data
adapters, PostgreSQL/DuckDB tracks, independently operated validators, and
Bittensor testnet evidence remain unfinished. Future-block entropy mixing is
also deferred. PlanRace must continue to display **LOCALNET EVIDENCE / TESTNET
PENDING** until those facts change.

- Checkpoint gate: publish regenerated v2 evidence, clean Git/Vercel provenance,
  and a reproducible reviewer pass.
- Final-submission gate: user-authorized dedicated testnet identities,
  registrations, signed multi-miner flow, timelock-aware weight readback, and a
  short end-to-end demo.
- Post-hackathon: PostgreSQL/DuckDB tracks, workload/private-data adapters,
  independently operated validators, and paid pilot discovery with database
  teams.

## Links

- Repository: https://github.com/dorakingx/planrace-subnet
- Evidence dashboard: https://planrace-subnet.vercel.app
- Protocol: `PROTOCOL_V2.md`
- Benchmark policy: `BENCHMARK_POLICY.md`
- Evidence index: `EVIDENCE_INDEX.md`

## Post gate

Do not post until P0 tests, localnet v2, clean GitHub/Vercel provenance, logged-out
HTTP checks, link/secret/dependency checks, and independent review all pass.
The public page checked 2026-09-05 confirms Checkpoint #1 on 2026-09-20 and
Final Submission on 2026-10-19. It displays the overall submission window ending
at 15:59 without a rendered timezone. Reconfirm the checkpoint's exact time and
timezone inside the authenticated form at posting.
