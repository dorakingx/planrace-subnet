# Results

## Protocol v2 mechanism simulation

The committed seeded simulation contains 512 replications, 24 epochs per
replication, 20 miner profiles, and eight named scenarios. Raw replication rows,
profile rows, summary, and a source/lock/artifact hash manifest are under
[`results/mechanism-v2/`](results/mechanism-v2/).

- honest-winner rate: 1.000;
- injected false-claim acceptance: 0 / 6,089 (false-acceptance rate 0.000);
- all-fail scenario no-new-update rate: 1.000;
- mean gaming weight: 0.000;
- mean honest weight: 0.8023; mean exact/near-copy profile weight: 0.1977;
- mean and maximum exact/near-copy behavior allocation gain: `0.0`;
- mean top-one share: 0.1256; observed maximum: 0.2500, equal to the cap;
- mean HHI: 0.1006; mean Gini: 0.1606;
- mean rank-stability Kendall tau-b: 0.5635; controlled hardware-only stability:
  1.000;
- mean cross-validator total-variation disagreement: 0.1427.

These are simulated mechanism properties, not throughput, testnet, customer, or
production-database results. The moderate cross-scenario rank statistic is kept
visible rather than described as universal agreement.

## Protocol v2 localnet

The verified run `localnet-v2-1788677901` completed 30 epochs on local netuid 3
with three rotating validator identities, ten miner identities, six query
families, 300 authenticated requests, and 270 signed responses. Every epoch
contained six or seven unique executable-strategy evaluations over eight hidden
fixtures.

Four identities passed all closed-schedule gates, representing four distinct
strategy portfolios. The signed local evidence policy used the mathematically
minimum four groups compatible with its 25% cap; each qualified portfolio
received 25%. The selective/copycat pair shared one evaluation in all 30 epochs,
failed the worst-family gate, and received zero. The mechanism-derived vector
finalized at extrinsic `16048-0002` and matched the Subtensor readback. Pairwise
validator Kendall tau-b values were 0.947, 0.947, and 1.0. These validators were three
identities under one operator, so this is repeatability evidence, not
independent consensus. See
[LOCALNET_V2.md](LOCALNET_V2.md) and
[`results/localnet-v2/`](results/localnet-v2/).

## Historical protocol v1 repeated mechanism spike

Across 20 repeated five-epoch simulations the honest indexed strategy beat the
correct baseline in 20/20 runs, remained exact in every epoch, and achieved a
score-ratio mean of 1.663 (range 1.640–1.682). The result-changing gaming profile
scored zero.

## Historical protocol v1 localnet E2E

On local netuid 2, signed requests reached Bob UID 1 and Charlie UID 2. Bob's
result hash equaled the reference and scored 9.083956; Charlie failed exactness
and scored zero. Weight `[UID 1 → 1.0]` finalized at extrinsic `1870-0002` and
read back as raw `[(1, 65535)]`. See
[`results/localnet-epoch-8.json`](results/localnet-epoch-8.json).

All results in this document use generated workloads. Nothing here is customer
data, a production engine result, or Bittensor testnet evidence.
