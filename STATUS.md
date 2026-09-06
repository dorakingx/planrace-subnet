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
- Final clean Python gate: 280 tests passed, Ruff and mypy clean, and branch
  coverage passed the 85% threshold.
- Seeded 512-replication v2 mechanism/adversary simulation with 0 false
  acceptance, 100% all-fail no-update, zero exact-duplicate allocation gain,
  and separately disclosed behavior-equivalent availability-replica gain
  (`results/mechanism-v2/`).
- Official local Subtensor netuid 3 setup with three development validator
  identities and ten heterogeneous miner identities.
- Verified 30-epoch protocol v2 localnet run: six query families, 300
  authenticated requests, 270 signed responses, 30 post-deadline reveals, four
  capped strategy allocations, finalized extrinsic `23608-0002`, matching
  readback, and a signed 31-source manifest. The complete run kept the local
  chain active from dispatch through readback and binds its aggregation policy
  into the signed summary.
- Required protocol, market, judging, evidence, and media drafts exist and state
  their gaps explicitly.
- A public-address-only, transaction-free testnet preflight now pins one SDK
  snapshot and reports endpoint, block, runtime, subnet, balance, UID/Axon,
  validator-permit, and readiness gates. Live read-only block `7945778` on
  runtime spec `454` passed canonical connectivity; wallet-dependent gates
  remain false.
- A separate transaction-free weight planner resolves public scored hotkeys to
  UIDs at one block/hash, reads the validator's existing weight row, checks
  permit/subnet/rate-limit gates, reproduces SDK max-weight clipping and u16
  quantization, and binds all submission parameters in a canonical SHA-256
  plan digest. A live v2 public testnet smoke check at block `7946333` passed
  all nine gates without constructing a transaction or requesting a signature;
  it did not use or claim PlanRace-owned identities.
- A post-submission read-only verifier validates the saved plan digest and later
  UID stability, permit, `last_update`, exact recipients, and quantized weights.
  A live unchanged-state check at block `7946228` failed closed on the expected
  later-block/update/recipient gates. It explicitly does not substitute for a
  finalized extrinsic receipt.
- A digest-authorized `weight-submit` boundary is implemented for the dedicated
  wallet and hard-coded `test` network. It revalidates plan age, signer, runtime,
  subnet parameters, UID bindings, prior weights, and exact u16 values before
  signing; SDK retries are disabled and its receipt remains incomplete until a
  later metagraph readback passes.
- A disposable, testnet-only wallet now exists with one coldkey, three named
  validator hotkeys, and ten named miner hotkeys. The local wallet directory
  and files are owner-only (`0700/0600`), secret material was not emitted, and
  only sanitized public addresses are tracked in
  `results/testnet/identities.public.json`. A canonical read-only snapshot at
  block `7946423` confirmed a zero test-TAO balance and no registrations, so no
  deployment claim is made.
- The editable 10-slide checkpoint deck is validated, visually reviewed, and
  stored at `submission/PlanRace_Checkpoint_Pitch.pptx`. It distinguishes the
  verified localnet result from the pending testnet gate.
- The signed v2 evidence drives the public dashboard. Dashboard format,
  typecheck, lint, build, evidence tests, route smoke tests, browser flows,
  accessibility, responsive layout, dependency audit, and public-link checks
  passed.
- The canonical production alias `https://planrace-subnet.vercel.app/` is READY;
  its Git-linked build provenance and public page, evidence, robots, and sitemap
  routes are checked on delivery.
- GitHub Actions passes the Python verification and complete dashboard jobs,
  including evidence audits, browser E2E, dependency audits, and secret scans.
- The public multi-architecture validator worker is available at immutable
  manifest digest `sha256:051d1cf58f127e5c7faa3945ad134027bc6931076a30791056c29aa82d3725b0`.
  Anonymous pull/runtime and source-bound GitHub attestation verification pass;
  see `WORKER_IMAGE.md`.

## Next gates

1. Rename the authenticated HackQuest draft to PlanRace and post Checkpoint #1;
   all six checkpoint reviews have no unresolved P0/P1 and the matching public
   deployment is ready.
2. Obtain the organizer/community test-TAO allocation for the public coldkey,
   then register the dedicated identities and execute the authorized testnet
   flow. The public testnet faucet is currently unavailable; never substitute
   real TAO or a mainnet wallet.

## Not complete

- Dedicated Bittensor testnet funding, registration, miner/validator interaction,
  scoring, weight transaction, and metagraph readback. Wallet creation itself
  is complete.
- Independently operated validators or independent hardware calibration.
- PostgreSQL/DuckDB and private customer-data adapters.
- HackQuest rename/checkpoint post, real-testnet demo/pitch videos, final
  submission, and release tag.

HackQuest still shows the earlier QECForge project with no checkpoint as last
observed. Reconfirm the portal's exact fields, video constraints, deadline time,
and timezone before any representational submission action.
