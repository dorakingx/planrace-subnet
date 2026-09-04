# Testnet

Status: **pending user-authorized dedicated wallet, faucet TAO, and wallet
signature**. Local public development keys must never be reused.

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
- actual testnet weight commit/set as required by the current runtime;
- finalized extrinsic IDs/block hashes and metagraph/weights readback;
- a separately signed testnet evidence manifest and raw epoch evidence.

## Operator procedure

1. Recheck current official Bittensor testnet registration, faucet, staking,
   endpoint, commit/reveal, and weight requirements against the installed SDK and
   current runtime.
2. Create a dedicated testnet wallet locally; never print mnemonic/seed/private
   key into logs, screenshots, repository, shell history, or evidence.
3. Obtain faucet TAO and register only after the user authorizes the wallet
   action. Record public addresses, netuid, UIDs, runtime spec, and transaction
   hashes.
4. Publish sanitized miner endpoints, run the real signed protocol flow, and
   preserve failures as evidence.
5. Submit mechanism-derived weights, wait for finalization, query readback, then
   sign and verify the testnet manifest.
6. Update the dashboard/video only from that committed manifest. Keep localnet
   and testnet panels visually and semantically separate.

No mainnet, paid service, valuable key, or production customer data is
authorized. Historical v1 and protocol v2 localnet evidence must never be
labeled testnet.
