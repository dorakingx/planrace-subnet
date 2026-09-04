# HackQuest checkpoint proposal

Status: **draft — do not post while testnet and clean deployment evidence are pending**.

## Project

**PlanRace — The competitive market for verified query plans.**

PlanRace is a Bittensor subnet prototype where miners compete to return bounded,
executable SQL rewrite and index artifacts for an already-correct query.
Validators create a precommitted challenge, authenticate requests, verify
miner-signed responses, reveal multiple hidden generated fixtures after the
deadline, require exact result equality, and only then score robust performance
relative to the unmodified baseline.

## Checkpoint progress

- Protocol v2 removes deterministic seed disclosure from public task IDs and
  uses independent OS-CSPRNG seeds and salts with post-deadline reveal.
- Requests are receiver-bound using Bittensor HTTP authentication; responses
  carry a miner sr25519 signature and replay window.
- Candidate SQL and indexes execute only inside disposable, resource-capped
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

## Current limits

The current execution track is SQLite on generated data. Private customer-data
adapters, PostgreSQL/DuckDB tracks, independently operated validators, and
Bittensor testnet evidence remain unfinished. Future-block entropy mixing is
also deferred. PlanRace must continue to display **LOCALNET EVIDENCE / TESTNET
PENDING** until those facts change.

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
