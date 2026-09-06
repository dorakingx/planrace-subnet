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
- Status: completed at hardened source review. No P0. Index-order digest and
  ordered-pair distribution P1 findings were fixed; setup sampling and broader
  type/collation localnet coverage remain documented limitations.

## Reviewer B — Bittensor mechanism

- Verify SDK/runtime compatibility, registered hotkey↔UID binding, endpoint
  publication, request/response identity, schedule, allocation, set/commit
  behavior, finalized extrinsic, and metagraph/weights readback.
- Ensure three local validators are described as identities under one operator,
  never independent operation.
- Status: completed at hardened localnet review. No P0. Finalized
  hotkey-to-UID resolution and transcript-to-observation auditing P1 findings
  were fixed. Testnet remains pending and is not claimed.

## Reviewer C — security

- Attempt seed/salt/fixture reconstruction from public task, task ID, and source.
- Tamper receiver/task/nonce/artifact/signature; replay request and response.
- Exercise malformed UTF-8/JSON, oversized and partial response, SQL/DDL escape,
  network/filesystem access, timeout, worker crash/OOM, and supply-chain digest.
- Rerun secret scans over history and working tree.
- Status: completed at hardened security review. No P0. Compression bomb,
  RFC6598 SSRF, headline-score audit, and public-signer claim P1 findings were
  fixed. Killable sync strategy isolation and hash-locked worker transitives
  remain documented hardening work.

## Reviewer D — mechanism design

- Reproduce honest, wrong, constant, malformed, timeout, copycat/Sybil,
  collusion proxy, validator-order, timing-outlier, curriculum-skew, and all-fail
  scenarios.
- Review family quotas, conservative uncertainty, duplicate portfolio split,
  no-new-update, 25% cap, HHI/Gini, validator disagreement, and rank correlation.
- Status: completed after independent reproduction. No P0/P1/P2. The prior
  staggered-absence portfolio-diversity bypass and unenforced per-family task
  minimum were fixed; both adversarial reproductions now fail closed.

## Reviewer E — hackathon judge

- Score all seven official criteria from 0–10 using only links in
  `JUDGING_MATRIX.md`; record missing evidence rather than awarding intent.
- Reject stale/dirty deployment, broken logged-out links, localnet-as-testnet,
  simulated demo footage, or unsupported market/production claims.
- Status: official-criteria evidence review completed at 49/70 (7.0/10).
  Checkpoint content is ready subject to a clean matching deployment and portal
  recheck. Final submission remains blocked on testnet and real media.

## Reviewer F — fresh evaluator

- From a clean environment, use only README to install, test, verify manifests,
  and explain the commodity/why-Bittensor/limitations in under two minutes.
- Record elapsed time, platform, commands, failures, and documentation changes.
- Status: completed on a clean clone plus final spot-check. No P0/P1/P2/P3.
  Bootstrap/readme prerequisites, full `make verify`, immediate audit progress,
  fast signature-only verification, secret baseline, and the two-minute project
  explanation were independently checked.

## Gate decision

- Checkpoint: **CONTENT PASS / PUBLICATION PENDING**. All six reviews are
  complete with no unresolved P0/P1. A matching production deployment and the
  authenticated HackQuest portal recheck remain before posting.
- Final: requires a second fresh review after testnet, media, portal submission
  draft, deployment, and release candidate are immutable.
