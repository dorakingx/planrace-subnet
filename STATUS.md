# Status

Updated: 2026-09-07 (Asia/Tokyo)

Public claim: **LOCALNET EVIDENCE / TESTNET PENDING**.

## Complete and verified

- HackQuest accepted PlanRace's project submission. The authenticated screen
  displayed `Successfully Submit Project`; an independent public readback
  returned `isSubmit=true` and the Bittensor Global Subnet Hackathon ID. See
  `submission/HACKQUEST_SUBMISSION_RECEIPT.md`. Acceptance does not establish
  competition eligibility or completion of the testnet requirements.
- Project description, repository/dashboard links, logo, project image, team
  introduction and a 62-second silent localnet dashboard video are saved.
  A public Development checkpoint and a Design checkpoint linking the full
  reviewed subnet proposal are posted and visible without authentication.
  Generic checkpoint publication does not prove organizer-specific acceptance
  of Checkpoint #1.
- A 4-minute-13-second narrated interim pitch is also saved and publicly
  accessible. Asset size and MD5 match the local file; full local decoding and
  all 39 subtitle/narration text comparisons passed. Full perceptual review and
  the actual testnet-result pitch remain pending; see `submission/MEDIA.md`.

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
- Published implementation CI at commit `826e9ff835f339699b28594772b510963fa7237c`
  passed 306 Python tests, Ruff, mypy over 35 source files and the 85% coverage
  gate. Dashboard E2E passed three tests. Run `34042058721` concluded success.
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
  validator permit/subnet-owner authorization, and readiness gates. Live
  read-only block `7945778` on runtime spec `454` passed canonical connectivity;
  wallet-dependent gates remain false.
- A separate transaction-free weight planner resolves public scored hotkeys to
  UIDs at one block/hash, reads the validator's existing weight row, checks
  permit-or-owner/subnet/rate-limit gates, reproduces SDK max-weight clipping
  and u16 quantization, and binds all submission parameters in a canonical
  SHA-256 plan digest. A live v2 public testnet smoke check at block `7946333` passed
  all nine gates without constructing a transaction or requesting a signature;
  it did not use or claim PlanRace-owned identities.
- A post-submission read-only verifier validates the saved plan digest and later
  UID stability, permit-or-owner authorization, `last_update`, exact recipients,
  and quantized weights.
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

1. Obtain the organizer/community test-TAO allocation for the public coldkey,
   then register the dedicated identities and execute the authorized testnet
   flow. The public testnet faucet is currently unavailable; never substitute
   real TAO or a mainnet wallet.
   Fresh read-only block `7947330`, runtime `454`, reports balance `0`, subnet
   creation price `1` test TAO and all 13 hotkeys unregistered. No transaction
   or signature was requested.
2. Produce the actual testnet demo and final pitch, including signed interaction,
   reveal, failure cases, scoring, aggregation, finalized weight readback and
   raw manifest verification. Interim localnet media do not satisfy this gate.
3. Complete the independent final review, release provenance and event-specific
   Checkpoint #1 acceptance check, then update the accepted project submission.

## Not complete

- Dedicated Bittensor testnet funding, registration, miner/validator interaction,
  scoring, weight transaction, and metagraph readback. Wallet creation itself
  is complete.
- Independently operated validators or independent hardware calibration.
- PostgreSQL/DuckDB and private customer-data adapters.
- Real-testnet demo/pitch videos, full final-review gates, and release tag.
- Organizer-specific Checkpoint #1 proposal acceptance, beyond the verified
  public Development checkpoint and project submission.

The accepted submission explicitly discloses testnet-pending status. The official
event still calls for a working testnet implementation and testnet demo in its
final deliverable. Do not close the overall goal on the portal receipt alone.
