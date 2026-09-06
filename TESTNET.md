# Testnet

Status: **pending user-authorized dedicated wallet, test-TAO allocation, and
wallet signature**. Local public development keys must never be reused.

Last read-only preflight: **2026-09-06**, block `7945778`, runtime spec `454`,
SDK `bittensor==11.1.0`, canonical endpoint
`wss://test.finney.opentensor.ai:443`. All mutable chain actions remain blocked
behind the user gate below.

The validator worker is already published for linux/amd64 and linux/arm64. The
testnet run must use this immutable reference and record it in its signed
manifest:

```text
ghcr.io/dorakingx/planrace-validator-worker@sha256:051d1cf58f127e5c7faa3945ad134027bc6931076a30791056c29aa82d3725b0
```

See `WORKER_IMAGE.md` for anonymous pull, SBOM, platform digests, and attestation
verification.

## Read-only preflight

The CLI has no wallet path, mnemonic, private-key, custom-RPC, registration, or
weight-setting option. A connectivity-only check is safe to run without a
wallet:

```bash
planrace testnet preflight
```

After dedicated public testnet identities exist, inspect one chain snapshot:

```bash
planrace testnet preflight \
  --netuid NETUID \
  --coldkey-ss58 PUBLIC_COLDKEY \
  --hotkey validator=PUBLIC_VALIDATOR_HOTKEY \
  --hotkey miner-a=PUBLIC_MINER_A_HOTKEY \
  --hotkey miner-b=PUBLIC_MINER_B_HOTKEY \
  --require-registered \
  --require-served-axon
```

The bounded JSON reports the exact endpoint, SDK/runtime version, block,
public balance, UID bindings, public Axons, validator permit, and readiness
gates. It explicitly distinguishes readiness for registration from readiness
for a protocol run. It is a latest-block diagnostic, not finalized transaction
evidence and not proof of wallet ownership. Never pass a seed, mnemonic, or
private key in place of a public address.

## Transaction-free weight plan

After registration and a protocol scoring run, resolve public miner hotkeys to
the UIDs at one exact block and inspect the validator's current weight row:

```bash
planrace testnet weight-plan \
  --netuid NETUID \
  --validator-hotkey-ss58 PUBLIC_VALIDATOR_HOTKEY \
  --score PUBLIC_MINER_A_HOTKEY=SCORE_A \
  --score PUBLIC_MINER_B_HOTKEY=SCORE_B
```

The command verifies the canonical testnet endpoint, block number/hash,
validator registration and permit, every scored hotkey binding, subnet minimum
recipient count, rate limit, and commit/reveal settings. It emits the prior
on-chain weight row, normalized proposed weights, and a canonical SHA-256 plan
digest. It exits nonzero unless all pre-signing gates pass.

This command remains strictly read-only: `transaction_constructed` and
`signature_requested` are always false, and there is no wallet path, custom RPC,
secret, submission, or mainnet option. The exact-block read is not itself proof
of finality. Re-run it immediately before a separately authorized signing step,
then bind the finalized submission and later readback—not this diagnostic alone—
into testnet evidence.

## Entry gate

Begin only after protocol v2 localnet evidence and manifest verification pass,
the dashboard derives from evidence, the repository/deployment are clean, and no
P0 security or mechanism finding remains. The required user action will be
presented as one concise `ACTION REQUIRED` step when those gates are satisfied.

## Intended minimum topology

- one dedicated testnet coldkey with separately named validator/miner hotkeys;
- at least one registered validator and two heterogeneous registered miners;
- public testnet Axon endpoints, receiver-bound signed requests, miner-signed
  responses, and replay rejection;
- a closed protocol v2 schedule with post-deadline reveal and isolated workers;
- actual testnet weight commit/set as selected by the pinned-block subnet
  hyperparameters;
- finalized commit extrinsic/block hash, timelock `reveal_round` when enabled,
  post-reveal `last_update`, raw weights, and metagraph readback;
- a separately signed testnet evidence manifest and raw epoch evidence.

## Operator procedure

1. Run `planrace testnet preflight`, then recheck current official Bittensor
   testnet registration, test-TAO allocation, staking, endpoint, commit/reveal,
   and weight requirements against the pinned SDK. Pin finalized blocks for
   transaction evidence; the preflight itself reads the latest block.
2. Create a dedicated testnet wallet locally; never print mnemonic/seed/private
   key into logs, screenshots, repository, shell history, or evidence.
3. Obtain test TAO through the currently designated community/hackathon
   allocation process and register only after the user authorizes the wallet
   action. Record public addresses, netuid, UIDs, finalized runtime spec, and
   transaction hashes.
4. Publish sanitized miner endpoints, run the real signed protocol flow, and
   preserve failures as evidence.
5. Run `planrace testnet weight-plan` to build weights by hotkey, inspect the
   existing row, and fail if any scored hotkey is absent or duplicated. Then
   resolve again against one recorded finalized metagraph snapshot immediately
   before an authorized submission.
6. Submit through SDK 11.1 `SetWeights`. It preflights registration/rate limits,
   conforms and quantizes the vector, then selects a direct set or a
   timelock-encrypted commit from the subnet's commit-reveal flag. A timelocked
   commit is auto-revealed by the chain; immediate readback is not completion.
7. Wait past the returned `reveal_round` when present, then query a new finalized
   block. Require the same hotkey-to-UID bindings, an advanced validator
   `last_update`, and normalized raw weights matching the submitted vector before
   calling the operation successful.
8. Sign and verify the testnet manifest, binding both finalized snapshots and
   all extrinsic/readback fields.
9. Update the dashboard/video only from that committed manifest. Keep localnet
   and testnet panels visually and semantically separate.

## No-new-update behavior

If the correctness, availability, diversity, or concentration gates fail,
PlanRace does not submit a new vector. This is not a chain-level reset: a prior
vector may remain active until another valid submission or the subnet's
activity-cutoff behavior removes its effect. The validator must alert on the
age of `last_update`; it must never label a skipped submission as cleared
weights.

## References

- Bittensor SDK `SetWeights` automatically selects direct or timelocked
  commit-reveal submission:
  <https://docs.learnbittensor.org/python-api/html/autoapi/bittensor/core/extrinsics/set_weights/index.html>
- The commit-reveal path exposes a `reveal_round` and requires explicit
  finalization/readback evidence:
  <https://docs.learnbittensor.org/python-api/html/_modules/bittensor/core/extrinsics/asyncex/commit_reveal.html>

No mainnet, paid service, valuable key, or production customer data is
authorized. Only the exact network alias `test` is accepted for this run;
mainnet aliases and arbitrary RPC URLs fail closed. Historical v1 and protocol
v2 localnet evidence must never be labeled testnet.
