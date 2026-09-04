# Status

Updated: 2026-09-05 (Asia/Tokyo)

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
  strategy splitting, fail-safe no-update, and weight concentration cap.
- 215 Python tests previously passed; Ruff and mypy clean. A final full rerun is
  required after evidence/dashboard integration.
- Seeded 512-replication v2 mechanism/adversary simulation with 0 false
  acceptance, 100% all-fail no-update, and negligible duplicated-strategy
  allocation gain (`results/mechanism-v2/`).
- Official local Subtensor netuid 3 setup with three development validator
  identities and ten heterogeneous miner identities.
- Verified 30-epoch protocol v2 localnet run: six query families, 300
  authenticated requests, 270 signed responses, 30 post-deadline reveals, five
  capped strategy allocations, finalized extrinsic `9062-0002`, matching
  readback, and a signed 31-source manifest.
- Required protocol, market, judging, evidence, and media drafts exist and state
  their gaps explicitly.

## Next gates

1. Drive the dashboard from the signed v2 manifest and rerun Python/dashboard,
   secret, dependency, browser, and public-link checks.
2. Push a clean GitHub commit and deploy/promote the same SHA to Vercel with
   `gitDirty=0`; record immutable provenance.
3. Run the independent checkpoint reviews. Do not post while a P0/critical issue
   is open.
4. Request exactly one user action for a dedicated testnet wallet/faucet/signature
   when local gates pass. Local public development keys must not be reused.

## Not complete

- Dedicated Bittensor testnet wallet, funding, registration, miner/validator
  interaction, scoring, weight transaction, and metagraph readback.
- Independently operated validators or independent hardware calibration.
- PostgreSQL/DuckDB and private customer-data adapters.
- Clean protocol v2 Vercel deployment and immutable deployment record.
- HackQuest rename/checkpoint post, real-testnet demo/pitch videos, final
  submission, and release tag.

HackQuest still shows the earlier QECForge project with no checkpoint as last
observed. Reconfirm the portal's exact fields, video constraints, deadline time,
and timezone before any representational submission action.
