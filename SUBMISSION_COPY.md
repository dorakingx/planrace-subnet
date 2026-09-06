# HackQuest submission copy

Status (2026-09-07 JST): project renamed to PlanRace and submitted to the
Bittensor Global Subnet Hackathon. A Development checkpoint and a Design
checkpoint linking the full proposal are posted. Demo and interim pitch are
published. Official Checkpoint #1 acceptance and real testnet execution remain
unverified/pending; a generic checkpoint post is not an organizer receipt.
See `submission/HACKQUEST_SUBMISSION_RECEIPT.md` for verified public state.

## Name

PlanRace

## Tagline

The competitive market for verified query plans.

## Short description

PlanRace is a Bittensor subnet where miners produce bounded structured index
plans for validator-owned SQL. Validators replay artifacts on unrevealed generated test
databases, require exact result equality, measure performance themselves,
and convert only correct scores into weights. It makes optimization open to
competing solvers with bounded, replayable verification. Verification being
economically cheaper than discovery is a hypothesis, not a measured result.

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

Uploaded `submission/planrace-logo.png` (800x800 PNG). The separate project
image is `submission/planrace-hackquest-1280x720.png` (1280x720 PNG).

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

Published interim asset: `submission/planrace-localnet-demo.mp4`, a 62-second
silent localnet evidence dashboard walkthrough. Public URL:
https://assets.hackquest.io/hackathons/projects/demoVideo/wuA6RfKG9HF2gCwIgWq_0.mp4

This does not satisfy the required real testnet recording. The final testnet
shot list and script remain in `SHOT_LIST.md`, `VOICEOVER.md` and `CAPTIONS.srt`.

## Pitch video

Published interim asset: `submission/planrace-interim-pitch.mp4`, a 253.527-second
narrated localnet pitch with an embedded English subtitle track. Public URL:
https://assets.hackquest.io/hackathons/projects/pitchVideo/lo7HDuBmzuPCI1PAqtkeg.mp4

HackQuest has separate Demo Video and Pitch Video fields. Full perceptual QA
and the final real-testnet pitch remain pending. See `submission/MEDIA.md`.

## Checkpoint update

Published as a Design checkpoint titled
“PlanRace: Subnet Proposal for Checkpoint #1”, with a link to the immutable
`CHECKPOINT_PROPOSAL.md` at commit `b1fc6c8c950a9c24f70cb870161b3b42d1ccba82`.
Its 200-character field is only a summary, not the full proposal. A separate
Development checkpoint is preserved. The exact payload is recorded in
`submission/HACKQUEST_CHECKPOINT_PAYLOAD.md`.

## Event submission form — observed 2026-09-07 JST

| Exact field/control | Required | Saved value |
|---|---|---|
| Select the Project to Submit | Yes | PlanRace (`da3b136a-c415-44cc-99cb-62c459e87f9f`) |
| What is your contract address? | Yes | The honest testnet-pending disclosure below |
| Which Prize Track Do You Belong To (Please select all that apply) | Yes | Grand Prizes |
| Submit | Action | Previously accepted; do not submit a duplicate merely to recheck status |

Saved deployment-address disclosure:

> Not yet deployed on public Bittensor testnet; no public subnet/contract address exists. Protocol v2 verified on local Subtensor only. Localnet evidence: https://planrace-subnet.vercel.app/ . Real testnet registration and weights are pending.

The form warns that deployment on the ecosystem is required to qualify. Portal
acceptance of the disclosure does not waive that requirement. No event-specific
Checkpoint #1 selector or separate proposal upload was visible in this form.

## Generic checkpoint form — observed 2026-09-07 JST

Type, Title and Description have required markers. Types are Idea, Design,
Development, Testing, Launch and Other. Title displays a limit of 50 and
Description a limit of 200. Link is optional. Up to three images can be added;
the form advertises 500x300 or 1280x720. Controls are Cancel and Post.
No checkpoint deadline time/timezone or organizer acceptance control was shown.

## Deadline evidence — observed 2026-09-07 JST

The official event says Checkpoint #1 is September 20 but gives no exact time
for that checkpoint. Its public page data gives the overall submission close
as `2026-10-19T15:59:00.000Z`, equivalent to October 20 at 00:59 JST. The
authenticated Brave Schedule tab displayed `Oct 20,2026 00:59`, consistently
with the JST environment, but did not label the timezone. Do not apply the
final submission timestamp to Checkpoint #1.

## Portal fields requiring live re-verification

For future updates, the current form must be re-read immediately before entry. Preserve exact labels,
required/optional status, character limits, accepted URL/file formats, track and
category selections, team fields, social/contact fields, video count/duration/
hosting, legal consent, and checkpoint/final-submit controls here before posting.
Legal acceptance, CAPTCHA, re-login, or 2FA requires user action.
