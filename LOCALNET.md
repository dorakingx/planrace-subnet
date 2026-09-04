# Localnet evidence

PlanRace has completed an end-to-end run on a real local Subtensor node: subnet
creation, activation, neuron registration, endpoint publication, receiver-bound
request authentication, unrevealed-fixture scoring, and a local-chain weight update.
This is local-chain evidence, not a testnet claim.

## Reproduce the data plane

Prerequisites are Docker, Python 3.12, and the repository bootstrap.

```bash
make bootstrap
make sync
docker compose -f compose.localnet.yaml up -d

# After creating/activating local netuid 2 and registering the public dev keys:
.bootstrap/bin/uv run python scripts/run_local_miner.py --profile honest --port 8091
.bootstrap/bin/uv run python scripts/run_local_miner.py --profile gaming --port 8092
.bootstrap/bin/uv run python scripts/run_local_epoch.py --epoch 8
```

Adding `--submit-local-weights` sends the derived plan to local netuid 2. The
script hard-codes network `local` and Bittensor's public `//Alice`, `//Bob`, and
`//Charlie` development identities. Never send funds to or reuse these keys.

## Observed chain

- Official image: `ghcr.io/raofoundation/subtensor-localnet:devnet`
- Pinned digest: `sha256:966520a59b71931d81cf14b0a2ef18e74e8541bab03653b1857ed29b51be4a28`
- Bittensor SDK: `11.1.0`; observed runtime `spec_version=452`
- Local subnet: netuid `2`, created at `428-0002`, activated at `710-0002`
- Validator: Alice, UID `0`
- Honest miner: Bob, UID `1`, endpoint `192.168.3.12:8091`
- Gaming miner: Charlie, UID `2`, endpoint `192.168.3.12:8092`

The validator delivered a receiver-bound signed request to each miner. The
responses were not signed in protocol v1 and are not described as authenticated.
Bob reproduced the reference hash and scored `9.083956420602034`; Charlie changed
the result and was hard-gated to zero. The derived `[UID 1: 1.0]` plan was accepted at
`1870-0002`, block hash
`0x04d1ed9f36009f55bd90e0115014b27561800ee10413c4f88a6a657f08c44e25`.
Readback showed raw weights `[(1, 65535)]` and `last_update=1870`.
Machine-readable chain evidence is in
[results/localnet-epoch-8.json](results/localnet-epoch-8.json). The independently
verifiable signed envelope, including explicit v1 limitations, is
[dashboard/evidence/localnet-v1-epoch-8.json](dashboard/evidence/localnet-v1-epoch-8.json).

## Local-only deviations

The official fast-block development image made the SDK's MEV-shielded
registration mortal era expire during one registration. Charlie was therefore
registered with a direct local extrinsic after confirming zero collateral share.
Commit/reveal weights were also disabled on this isolated chain to exercise the
plain weight extrinsic without that artificial timing race. Neither workaround
is a production or testnet procedure; testnet must retain the SDK's current
commit/reveal path.

Official references: [Bittensor local development](https://preview.bittensor.com/docs/guides/local-development),
[Subtensor](https://github.com/RaoFoundation/subtensor), and
[Bittensor SDK](https://github.com/opentensor/bittensor).
