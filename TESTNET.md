# Testnet

Status: **pending user-authorized dedicated wallet, test-TAO allocation, and
wallet signature**. Local public development keys must never be reused.

Last read-only preflight: **2026-09-05**, SDK `bittensor==11.1.0`, canonical
endpoint `wss://test.finney.opentensor.ai:443`. All mutable chain actions remain
blocked behind the user gate below.

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

1. Recheck current official Bittensor testnet registration, test-TAO allocation,
   staking, endpoint, commit/reveal, and weight requirements against the pinned
   SDK and a single finalized runtime block.
2. Create a dedicated testnet wallet locally; never print mnemonic/seed/private
   key into logs, screenshots, repository, shell history, or evidence.
3. Obtain test TAO through the currently designated community/hackathon
   allocation process and register only after the user authorizes the wallet
   action. Record public addresses, netuid, UIDs, finalized runtime spec, and
   transaction hashes.
4. Publish sanitized miner endpoints, run the real signed protocol flow, and
   preserve failures as evidence.
5. Build weights by hotkey, resolve them to UIDs from one recorded finalized
   metagraph snapshot, and fail if any scored hotkey is absent or duplicated.
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
