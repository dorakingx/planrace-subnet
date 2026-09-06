# Status

Updated: 2026-09-06 (Asia/Tokyo)

Public claim: **LOCALNET EVIDENCE / TESTNET PENDING**.

## Complete and verified

- Protocol v2 opaque OS-CSPRNG task creation and post-deadline commit/reveal.
- Strict structured index artifacts and allowlisted read-only rewrite boundary.
- Receiver-bound validator requests, miner-signed responses, and replay/expiry
  rejection.
- Disposable Docker evaluation with CPU, memory, network, query, and envelope
  limits; sandbox failures are observations rather than validator crashes.
- Canonical exact-result gate followed by baseline-relative cold/warm/setup/
  storage scoring across reuse horizons.
- Closed multi-family schedule, conservative multi-epoch aggregation, duplicate
  strategy splitting, explicit no-new-update, and weight concentration cap.
- Final clean Python gate: 232 tests passed, Ruff and mypy clean, and 87.12%
  branch coverage against the 85% threshold.
- Seeded 512-replication v2 mechanism/adversary simulation with 0 false
  acceptance, 100% all-fail no-update, and negligible duplicated-strategy
  allocation gain (`results/mechanism-v2/`).
- Official local Subtensor netuid 3 setup with three development validator
  identities and ten heterogeneous miner identities.
- Verified 30-epoch protocol v2 localnet run: six query families, 300
  authenticated requests, 270 signed responses, 30 post-deadline reveals, four
  capped strategy allocations, finalized extrinsic `5569-0002`, matching
  readback, and a signed 31-source manifest. The complete run kept the local
  chain active from dispatch through readback and binds its aggregation policy
  into the signed summary.
- Required protocol, market, judging, evidence, and media drafts exist and state
  their gaps explicitly.
- The signed v2 evidence drives the public dashboard. Dashboard format,
  typecheck, lint, build, evidence tests, route smoke tests, browser flows,
  accessibility, responsive layout, dependency audit, and public-link checks
  passed.
- Clean protocol v2 preview `dpl_5UKpTxYdNhskbUH85VrWponn7j4a` was verified
  and its artifact promoted as production `dpl_6CxN3ZqYYm7sArcfEwWNDHQDpuYD`.
  The corrected `dashboard` project root then produced Git-linked production
  `dpl_3JB3i2sG3kyHFAznCQwSh4iukqie` from exact GitHub SHA `d5ce868` with a clean
  build log and passing public checks.
- GitHub Actions passed both Python verification and the complete dashboard
  job after the cross-platform evidence-audit correction.

## Next gates

1. Run the independent checkpoint reviews. Do not post while a P0/critical issue
   is open.
2. Request exactly one user action for a dedicated testnet wallet/faucet/signature
   when local gates pass. Local public development keys must not be reused.

## Not complete

- Dedicated Bittensor testnet wallet, funding, registration, miner/validator
  interaction, scoring, weight transaction, and metagraph readback.
- Published digest-pinned testnet worker/materializer image; the localnet run
  records only a local Docker content ID and host-specific SQLite file hashes.
- Independently operated validators or independent hardware calibration.
- PostgreSQL/DuckDB and private customer-data adapters.
- HackQuest rename/checkpoint post, real-testnet demo/pitch videos, final
  submission, and release tag.

HackQuest still shows the earlier QECForge project with no checkpoint as last
observed. Reconfirm the portal's exact fields, video constraints, deadline time,
and timezone before any representational submission action.
