# HackQuest submission copy

Status: checkpoint copy passed; authenticated portal re-read, project rename,
and posting remain. Localnet v2 and clean deployment gates pass. Testnet claims
below remain explicitly pending.

## Name

PlanRace

## Tagline

The competitive market for verified query plans.

## Short description

PlanRace is a Bittensor subnet where miners produce bounded structured index
plans for validator-owned SQL. Validators replay artifacts on unrevealed generated test
databases, require exact result equality, measure performance themselves,
and convert only correct scores into weights. It makes optimization open to
competing solvers while keeping verification cheap, objective, and reproducible.

Protocol v2 removes the deterministic public seed leak, signs both directions,
evaluates only inside disposable resource-capped workers, and aggregates a
closed multi-family schedule with copy/Sybil-aware weights. The published
epoch-8 artifact remains historical v1 evidence with its seed-leak and unsigned
response limitations intact. No testnet result is claimed yet.

## Long description

Database-native optimizers are powerful but remain one engine/vendor's decision
system. PlanRace tests a complementary open market: independent miners may use
rules, search, learned systems, or engine expertise to produce a bounded
executable artifact for an already-correct query. The validator owns the oracle.
It commits hidden generated fixtures, authenticates each miner request, verifies
the signed response after a sealed deadline, and requires canonical result
equality before measuring any speedup.

Exact and compliant strategies are compared with the same-fixture baseline on
cold/warm latency, setup, storage, and multiple reuse horizons. Repeated
observations span multiple query families; uncertainty, availability,
correctness, compliance, copied artifacts, and concentration are enforced before
the validator produces a Bittensor weight vector. Raw signed evidence lets a
reviewer audit the claims without trusting the dashboard.

Current scope is generated SQLite workloads. Testnet, PostgreSQL/DuckDB, private
buyer adapters, and independently operated validators are milestones, not
completed claims.

## Logo

Use the PlanRace green database/verification mark from the deployed site's
`dashboard/app/icon.svg`. Reconfirm the portal's accepted file type, dimensions,
and size before upload.

## Repository

https://github.com/dorakingx/planrace-subnet

## Website

https://planrace-subnet.vercel.app

## Miner task

Given the public schema, known-correct reference query, public workload
distribution, pinned engine/sandbox identity, and artifact budget, discover and
return a strict executable optimization bundle before the deadline. The response
must be signed by the registered miner hotkey. Miners never self-report timing or
correctness and never receive hidden fixture seed/salt material before reveal.

## Validator task

Create an independently randomized precommitted challenge; sign receiver-bound
requests; seal submissions at the deadline; reveal and verify multiple hidden
fixtures; execute reference and candidate only in disposable workers; gate on
canonical exact equality and compliance; measure baseline-relative cost across
reuse horizons; aggregate repeated multi-family observations; submit the
eligible weight vector; and publish a signed manifest with extrinsic/readback.

## Mechanism

Correctness precedes performance. Any signature, replay, deadline, SQL-policy,
resource, or exact-result failure is unavailable/zero. Eligible strategies earn
conservative baseline-relative reward. Duplicate strategy digests share one
portfolio contribution; closed schedule coverage and availability/correctness/
compliance thresholds apply; no strategy exceeds the configured weight cap; an
all-fail round produces no update.

## Users and roadmap

Database teams, engine vendors, and data platforms need recurring optimization
as workloads and releases change. After the SQLite mechanism proof: testnet
multi-miner operation, disposable workers, DuckDB analytical tasks, PostgreSQL
parameter distributions, independent validators, and buyer-provided workloads.

Disposable workers are now implemented for the SQLite proof. Roadmap order:
dedicated Bittensor testnet flow and evidence; independent validator calibration;
DuckDB/PostgreSQL tracks; privacy-preserving workload adapters; distributed
benchmark capacity; buyer staging/rollback integrations.

## Team and contact

Use the existing HackQuest account/team values. Do not invent additional members,
social handles, email addresses, or affiliations. Reconfirm which of these fields
the current portal exposes.

## Demo video

Pending a real testnet recording. Use `SHOT_LIST.md`, `VOICEOVER.md`, and
`CAPTIONS.srt`. Do not upload simulation or localnet footage as the required
testnet segment. Reconfirm count, duration, privacy, and hosting requirements.

## Pitch video

Pending. Use `PITCH_SCRIPT.md`; include the real testnet result and limitations.
Reconfirm whether HackQuest provides separate demo/pitch fields or a single
video field before recording.

## Checkpoint update

Use `CHECKPOINT_PROPOSAL.md`; its content gate passes. The paste-ready field map
is `submission/HACKQUEST_CHECKPOINT_PAYLOAD.md`.

## Portal fields requiring live re-verification

The current form must be re-read immediately before entry. Preserve exact labels,
required/optional status, character limits, accepted URL/file formats, track and
category selections, team fields, social/contact fields, video count/duration/
hosting, legal consent, and checkpoint/final-submit controls here before posting.
Legal acceptance, CAPTCHA, re-login, or 2FA requires user action.
