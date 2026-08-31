# Results

## Repeated mechanism spike

Across 20 repeated five-epoch simulations the honest indexed strategy beat the
correct baseline in 20/20 runs, remained exact in every epoch, and achieved a
score-ratio mean of 1.663 (range 1.640–1.682). The result-changing gaming profile
scored zero.

## Localnet E2E

On local netuid 2, signed requests reached Bob UID 1 and Charlie UID 2. Bob's
result hash equaled the reference and scored 9.083956; Charlie failed exactness
and scored zero. Weight `[UID 1 → 1.0]` finalized at extrinsic `1870-0002` and
read back as raw `[(1, 65535)]`. See
[`results/localnet-epoch-8.json`](results/localnet-epoch-8.json).

These are generated-workload and local-chain results, not customer or testnet data.
