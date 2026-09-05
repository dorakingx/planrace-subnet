# Checkpoint review gate

Status: **not passed**. This file is the review worksheet; scores/sign-off must
not be filled before the referenced evidence exists. A P0 or critical finding
blocks the HackQuest checkpoint.

## Reviewer A — database systems

- Recompute ordered/unordered canonical SQL result semantics, including NULL,
  numeric, text/bytes, duplicate-row, collation, and intentional-empty cases.
- Inspect hidden workload construction, public distribution usefulness, cache
  interleaving, setup/storage accounting, reuse horizons, and index-plan usage.
- Challenge any claim that finite SQLite fixtures imply universal equivalence or
  production-engine performance.
- Status: pending full localnet v2 evidence and fresh run.

## Reviewer B — Bittensor mechanism

- Verify SDK/runtime compatibility, registered hotkey↔UID binding, endpoint
  publication, request/response identity, schedule, allocation, set/commit
  behavior, finalized extrinsic, and metagraph/weights readback.
- Ensure three local validators are described as identities under one operator,
  never independent operation.
- Status: local-chain v2 final vector pending; testnet pending.

## Reviewer C — security

- Attempt seed/salt/fixture reconstruction from public task, task ID, and source.
- Tamper receiver/task/nonce/artifact/signature; replay request and response.
- Exercise malformed UTF-8/JSON, oversized and partial response, SQL/DDL escape,
  network/filesystem access, timeout, worker crash/OOM, and supply-chain digest.
- Rerun secret scans over history and working tree.
- Status: implementation tests exist; fresh integrated run and source-artifact
  signature audit pending.

## Reviewer D — mechanism design

- Reproduce honest, wrong, constant, malformed, timeout, copycat/Sybil,
  collusion proxy, validator-order, timing-outlier, curriculum-skew, and all-fail
  scenarios.
- Review family quotas, conservative uncertainty, duplicate portfolio split,
  no-new-update, 25% cap, HHI/Gini, validator disagreement, and rank correlation.
- Status: 512-replication simulation complete; localnet rank evidence pending.

## Reviewer E — hackathon judge

- Score all seven official criteria from 0–10 using only links in
  `JUDGING_MATRIX.md`; record missing evidence rather than awarding intent.
- Reject stale/dirty deployment, broken logged-out links, localnet-as-testnet,
  simulated demo footage, or unsupported market/production claims.
- Status: pending clean deployment, testnet, media, and portal recheck.

## Reviewer F — fresh evaluator

- From a clean environment, use only README to install, test, verify manifests,
  and explain the commodity/why-Bittensor/limitations in under two minutes.
- Record elapsed time, platform, commands, failures, and documentation changes.
- Status: pending final public commit.

## Gate decision

- Checkpoint: **BLOCKED** until every status above is complete and no P0/critical
  finding remains.
- Final: requires a second fresh review after testnet, media, portal submission
  draft, deployment, and release candidate are immutable.
