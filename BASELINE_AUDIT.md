# PlanRace Protocol v2 Baseline Audit

Captured before implementation changes on **2026-09-01T06:00:52+09:00**
(2026-08-31T21:00:52Z). This document separates observed facts from planned
work. It contains no wallet secret, mnemonic, token, or private key.

## Git working tree

| Field | Observed value |
| --- | --- |
| Existing working tree | `/Users/hatanakatomoya/Developer/App/planrace-subnet` |
| Pre-change branch | `main` |
| Pre-change status | clean; `main...origin/main` |
| Pre-change HEAD | `3bf091901c4867725f2013cff2d2a64d84801861` |
| HEAD authored at | `2026-08-31T21:52:27+09:00` |
| HEAD subject | `feat: deploy dashboard to Vercel` |
| Remote | `origin https://github.com/dorakingx/planrace-subnet.git` (fetch/push) |
| Working branch created after capture | `hardening/protocol-v2` |

No duplicate checkout was created. This branch starts exactly at the recorded
`main` HEAD. No force push is permitted.

## GitHub

| Field | Observed value |
| --- | --- |
| Repository | <https://github.com/dorakingx/planrace-subnet> |
| Visibility | public |
| Default branch | `main` |
| GitHub `main` SHA | `3bf091901c4867725f2013cff2d2a64d84801861` |
| Latest successful CI | [run 33393944979](https://github.com/dorakingx/planrace-subnet/actions/runs/33393944979) |
| CI head SHA | `3bf091901c4867725f2013cff2d2a64d84801861` |
| CI event / conclusion | `push` / `success` |
| CI completed | `2026-08-31T12:54:39Z` |

## Vercel production

| Field | Observed value |
| --- | --- |
| Production alias | <https://planrace-subnet.vercel.app> |
| Deployment ID | `dpl_HLPqecmik1wKZQtRMy4pZm7Zj3Jw` |
| Immutable URL | <https://planrace-subnet-n9z5hptfj-doraking.vercel.app> |
| State | `READY` |
| Source | Vercel CLI |
| Created | `2026-08-31T21:51:25+09:00` |
| Vercel `gitCommitSha` | `4b932604b17c18c128b4842805ff0c45ec9ea7f7` |
| Vercel `gitCommitRef` | `main` |
| Vercel `gitDirty` | `1` |
| Logged-out `/` | HTTP 200 |
| Logged-out `/og.png` | HTTP 200, `image/png` |
| Logged-out `/favicon.ico` | **HTTP 404** |

### Provenance mismatch

The production deployment does **not** match GitHub `main`. It was created
from a dirty CLI working tree whose metadata points at commit `4b932604...`.
The later commit `3bf0919...` was authored at `21:52:27+09:00`, about 62 seconds
after the production deployment was created. This timing and the deployment
metadata explain the mismatch: the dashboard was deployed before its final
source state was committed.

The next production deployment must be made only after the complete source is
committed and pushed. Acceptance requires Vercel `gitCommitSha` equal to the
GitHub `main` SHA, `gitDirty=0`, READY state, and re-verification of the alias,
OG image, favicon, links, browser console, mobile layout, and security headers.

## HackQuest

Observed from the authenticated project setup page at
`/projects/setup/da3b136a-c415-44cc-99cb-62c459e87f9f?tab=checkpoints`.

| Field | Observed value |
| --- | --- |
| Current project name | `QECForge` |
| Project intro | empty |
| Completion indicator | `0`, “Incomplete Project” |
| Checkpoints | none; UI says “Record your first checkpoint” |
| Checkpoint action available | `Add Checkpoint` |

No HackQuest field was changed and no checkpoint was posted during this
audit. The project must be renamed to PlanRace before a checkpoint is posted,
after all P0 posting gates pass.

## Bittensor testnet readiness

| Field | Observed value |
| --- | --- |
| Python SDK in project environment | `bittensor 11.1.0` (current PyPI release at capture) |
| Project-environment CLI | `.venv/bin/btcli 11.1.0`; no global `btcli` on PATH |
| Official test endpoint selected by SDK | `wss://test.finney.opentensor.ai:443` |
| Test runtime spec / observed block | `452` / `7,905,665` |
| Test subnet inventory | 556 netuids observed; none owned or allocated to PlanRace |
| Dedicated testnet wallet | Baseline: absent. Created after explicit authorization on 2026-09-06 as disposable testnet-only wallet `planrace-testnet`; public identities are in `results/testnet/identities.public.json` |
| Testnet hotkeys | none observed |
| Testnet netuid | none allocated or recorded |
| Test TAO | `0` at canonical testnet block `7946423`; organizer/community allocation pending |
| Existing chain evidence | local chain only, netuid `2`; explicitly not testnet |

Wallet creation, mnemonic backup, faucet use, and any required wallet signing
remain user-gated operations. Mainnet aliases, arbitrary RPC endpoints, and
reuse of local development keys must fail closed.

## Immediate P0 gaps

- Protocol v1 exposes deterministic task material and is historical evidence,
  not an acceptable testnet protocol.
- Miner responses are not yet signed.
- The production page contains claims and counters that are not generated from
  a signed evidence manifest.
- The production deployment provenance is dirty and stale.
- Favicon verification fails.
- HackQuest still identifies the project as QECForge and has no checkpoint.
- At baseline there was no testnet wallet, netuid, TAO, deployment, or testnet
  evidence. The post-baseline dedicated wallet is now present, but it has no
  test TAO, netuid, registration, or protocol execution evidence yet.
