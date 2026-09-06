# HackQuest Checkpoint #1 Portal Payload

Status: **content approved; authenticated paste/post pending**.

Use this only for project
`da3b136a-c415-44cc-99cb-62c459e87f9f` in the Bittensor Global Subnet
Hackathon. Before submitting, confirm that the portal still shows the same
project ID and Checkpoint #1. Do not accept legal terms, solve CAPTCHA, or alter
team/contact data without the account owner.

## Overview portal payload

- **Logo:** `submission/planrace-logo.png` (800×800 PNG)
- **Name:** PlanRace
- **Intro:** The competitive market for verified query plans.
- **Sector:** AI, Infra
- **Tech tags:** Python, React, Next, Web3, Node
- **MVP link:** https://planrace-subnet.vercel.app/
- **Project/open-source link:** https://github.com/dorakingx/planrace-subnet
- **X link:** Leave blank unless the account owner supplies one.
- **Project image:** `submission/planrace-hackquest-1280x720.png` (1280×720 PNG)
- **Demo video:** Pending; do not invent a URL.
- **Pitch video:** Pending; do not invent a URL.
- **Fundraising status:** Bootstrapped; no external funding.
- **Active hackathon:** Bittensor Global Subnet Hackathon
- **Deployment ecosystem:** Bittensor
- **Network:** Testnet
- **Contract address/deployed link:** Leave blank while testnet is pending. The
  public dashboard is a Vercel deployment, not a Bittensor testnet deployment.

### Overview description

PlanRace is a Bittensor subnet prototype where miners compete to produce
bounded, executable structured index plans for validator-owned, already-correct
SQL. Validators replay every candidate against hidden workloads in disposable,
network-disabled workers and reward only exact, policy-compliant results.

The protocol uses receiver-bound signatures, replay and deadline controls,
opaque commit/reveal fixtures, deterministic artifact digests, strict resource
budgets, robust baseline-relative scoring, and duplicate/Sybil allocation
controls. Miners may use any optimization technique, but they never supply raw
DDL or self-reported benchmark results.

Protocol v2 is implemented and verified on an official local Subtensor image.
The 30-epoch localnet run recorded 300 authenticated requests, 270 signed
responses, 30 post-deadline reveals, contained adversarial failures, and a
finalized mechanism-derived local-chain weight readback. A 512-replication
adversarial simulation recorded zero false acceptance and zero exact-duplicate
allocation gain. These are localnet results, not testnet claims. Real testnet
registration and weights remain pending.

### Project progress

Built protocol v2, authenticated wire messages, isolated executable-artifact
evaluation, robust scoring and anti-duplication controls, a verified 30-epoch
3-validator/10-miner localnet run, signed public evidence, an adversarial
simulation, a public evidence dashboard, a multi-architecture validator worker
image, dedicated testnet identities, and fail-closed testnet
planning/submission/readback tooling. Test TAO, live testnet registration,
public Axons, testnet weights, and finalized metagraph evidence remain pending.

## Project name

PlanRace

## Tagline

The competitive market for verified query plans.

## Checkpoint title

PlanRace — Verified Query Optimization Subnet Proposal

## Checkpoint body

PlanRace is a Bittensor subnet prototype where miners compete to produce
bounded, executable structured index plans for validator-owned, already-correct
SQL. Database teams repeatedly retune important queries as data distributions,
traffic, schemas, and engine versions change. PlanRace turns that recurring
search problem into an open market while keeping validation objective and
replayable.

Validators publish the schema, known-correct query, public training workload,
engine/sandbox identity, resource budget, and an opaque commitment. They send
receiver-bound signed challenges to miners. Miners may use rules, program
search, learned systems, or engine expertise, but return only a strict
`OptimizationBundle` containing a bounded `IndexSpec` list and a signed
artifact digest. Raw arbitrary DDL and miner-supplied benchmark claims are not
accepted.

After the deadline, the validator seals submissions and reveals independently
randomized hidden fixtures. Every candidate runs in a disposable,
network-disabled, resource-capped worker. Signature, replay, deadline, policy,
resource, or exact-result failures receive zero before performance matters.
Correct artifacts are compared with the same-fixture baseline across cold and
warm latency, setup cost, storage cost, and multiple reuse horizons. A closed
multi-family schedule aggregates conservative measurements; duplicates split
one strategy contribution, behavior groups are capped, and an all-fail round
creates no new weight update.

Protocol v2 and its mechanism proof are implemented. The verified localnet run
used three validator identities under one operator and ten heterogeneous miners
for 30 epochs: 300 authenticated requests, 270 signed responses, 30
post-deadline reveals, adversarial failures contained, and a finalized
mechanism-derived local-chain weight/readback. A 512-replication adversarial
simulation recorded zero false acceptance and zero exact-duplicate allocation
gain. These are explicitly localnet results, not testnet claims.

A dedicated testnet-only identity set now exists with three validator and ten
miner hotkeys. Test-TAO allocation, registration, public Axons, real testnet
interaction, weight transaction, and metagraph readback remain pending. The
public dashboard therefore continues to show LOCALNET EVIDENCE / TESTNET
PENDING.

Repository: https://github.com/dorakingx/planrace-subnet

Evidence dashboard: https://planrace-subnet.vercel.app/

## Progress during the hackathon

Protocol v2 security hardening, structured artifacts, signed bidirectional
messages, isolated evaluation, robust scoring, duplicate/Sybil controls,
adversarial simulation, 3-validator/10-miner localnet execution, signed raw
evidence, public dashboard, dedicated testnet identities, and fail-closed
testnet planning/submission/readback tooling are complete. The next milestone is
the funded real testnet run and demo.

## Repository URL

https://github.com/dorakingx/planrace-subnet

## Project URL

https://planrace-subnet.vercel.app/

## Upload, if the checkpoint accepts a deck

`submission/PlanRace_Checkpoint_Pitch.pptx`

## Final pre-submit checks

- The page is the Bittensor Global Subnet Hackathon Checkpoint #1 form.
- The project name is changed from QECForge to PlanRace.
- Repository and website URLs are clickable while logged out.
- No field truncates the checkpoint body silently.
- No testnet-live, independent-validator, production-engine, or customer-data
  claim has been added.
- After submission, preserve the visible accepted/submitted state and public
  checkpoint URL or ID.
