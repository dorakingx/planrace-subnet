# Updated subnet proposal

## Commodity

An executable, bounded query-optimization artifact: a structured index plan and,
where the track permits it, an approved SQL rewrite for an already-correct
query. The deliverable is reusable and auditable; it is not a generated answer.

## Participants

- Buyers define a safe schema, public workload distribution, correctness query,
  constraints, and reuse horizons through a future adapter.
- Validators precommit independently randomized hidden fixtures, sign
  receiver-bound challenges, run the exact-result oracle and isolated benchmark,
  aggregate repeated observations, and set weights.
- Miners may use any optimization technique but return only the strict protocol
  bundle. They never supply their own score or timing evidence.

## Mechanism

1. Publish immutable engine/sandbox identity, schema, reference SQL, parameter
   domain, family, artifact budget, and commitment—but no hidden seed or salt.
2. Seal the submission set at the deadline, then reveal the committed material.
3. Execute reference and candidate only in disposable workers across multiple
   hidden fixtures.
4. Reject semantic mismatch, disallowed SQL/index DDL, deadline failure,
   resource failure, or signature/replay failure before performance matters.
5. Score eligible strategies relative to the same-fixture baseline across cold,
   warm, setup, storage, and multiple reuse horizons.
6. Aggregate a closed multi-family schedule with conservative uncertainty,
   availability/correctness/compliance thresholds, duplicate-strategy splitting,
   and a per-strategy weight cap.
7. Submit the final positive vector and preserve extrinsic plus metagraph
   readback in a validator-signed manifest.

## Why Bittensor

Optimization discovery is open-ended and can reward specialized rules, search,
learned systems, and engine expertise. Verification is narrower: a validator can
replay a bounded artifact, compare canonical results, and benchmark under a
committed policy. Bittensor provides continuing competition, independent
validator judgment, and weight-based incentives instead of a single solver API.

## Safety scope

Raw arbitrary SQL is not accepted. Protocol v2 admits one read-only SELECT and a
strict structured `IndexSpec`; approved rewrites are parsed and allowlisted.
Evaluation occurs outside the validator process with filesystem, network,
memory, CPU, response-size, and query-time limits. Customer rows are not part of
the current proof, and a privacy-preserving buyer adapter remains future work.

## Evidence and roadmap

The committed mechanism simulation and localnet v2 evidence establish the
SQLite mechanism. Next gates are a dedicated testnet wallet and faucet TAO,
testnet registration and signed multi-miner flow, clean public deployment, and
independent validation. Subsequent tracks target DuckDB/PostgreSQL, validator
diversity, workload adapters, and a distributed benchmark fleet.
