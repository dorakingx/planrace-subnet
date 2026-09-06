# Protocol v2 localnet evidence

Status: **VERIFIED localnet evidence; TESTNET PENDING**.

## Topology

- Official Subtensor local development container, SDK Bittensor 11.1.0.
- Netuid 3, runtime spec 424.
- Three deterministic public development validator identities, all controlled by
  one operator on one machine.
- Ten deterministic public development miner identities with heterogeneous
  profiles: baseline, four useful optimization variants, hybrid, over-budget,
  constant-answer attempt, timeout/resource attempt, and copycat/Sybil.
- 30 closed-schedule epochs rotating the three validator identities.

These development identities use no valuable secret and must never be reused on
testnet or mainnet.

The profile named `partial-index` exercises the strict structured index track.
Protocol v2 follows the brief's first safety preference—fixed validator-owned
reference SQL plus structured index selection—and does not claim rewrite safety.
The constant-answer attempt likewise has no result field to exploit and collapses to
the no-index executable strategy; it is still distinguishable in the signed
response metadata but receives no special correctness shortcut.

## Local-chain preparation disclosure

The local runtime's development defaults prevented the required short test cycle
and its drand service was unavailable. Using the public local sudo identity only,
the operator set the local admin freeze window to zero and disabled runtime
commit/reveal on netuid 3. Protocol v2 still performs its own application-layer
task commitment, deadline, sealed submission set, and reveal. This exception is
local-only and is not evidence for a testnet configuration.

The final evidence run kept Subtensor active from request dispatch through
weight readback. Paired same-worker baseline ratios reduce shared-host timing
noise, but do not eliminate it; this limitation is included in the signed
manifest.

## Full run

The authoritative command is:

```bash
.bootstrap/bin/uv run python -u scripts/run_localnet_v2.py \
  --epochs 30 --netuid 3 \
  --worker-image sha256:8685473bb8d2ea75f5a3ab4021ad1f9f72552d6efeee240df13f25f40e5f3aef \
  --chain-image sha256:592aa28d528ebadba5f83807d0d38e29fa954dd91ac3e180b48259d64a654e8f \
  --evaluation-workers 3 \
  --output .localnet-state/localnet-v2-continuous-final
```

Verified evidence checks:

- exactly 30 epoch records and 300 signed validator requests;
- exactly nine accepted miner responses per epoch (the timeout profile is the
  sole intended transport failure);
- hidden reveal only after the final request deadline;
- seven unique strategy evaluations in 27 epochs and six in the three
  intentional-zero-result epochs because exact duplicate artifacts are
  evaluated once and the timeout profile is unavailable;
- over-budget and timeout profiles receive no reward; baseline-equivalent and
  selective/copycat profiles fail the worst-family reward gate;
- pairwise validator ranking correlation is reported, not assumed;
- the final mechanism-derived vector is actually submitted and read back;
- `manifest.json` verifies under the externally expected public development
  signer and binds the summary plus all 30 epoch files by SHA-256. Because the
  development signing URI is public, this signature is a tamper-evident
  checksum—not proof of an independent operator.

The completed run is `localnet-v2-1788674678`, bound to Git commit
`a0a97bba370229b47661dfec4e665ef1723ba4e3`. It produced 300 authenticated
requests and 270 signed responses across six query families. The signed summary
binds the local evidence policy: at least 24 tasks, three tasks per family, 75%
availability, 95% compliance and correctness, four distinct eligible behavior
portfolios, and a 25% per-portfolio cap. Four useful portfolios qualified and
received 25% each. The selective/copycat pair was grouped into one evaluation
in every epoch, failed the worst-family gate, and received zero weight.

The mechanism-derived vector finalized successfully at extrinsic `5569-0002`,
block `0x173019072bd83d2957a926b1e9e67ebaa1ddffa4835433f43718e88a05a9c72c`.
The local Subtensor readback contained UIDs 5–8 at exactly 25% each. All three
validator-identity ranking pairs reported Kendall tau-b 1.0. The signed payload
SHA-256 is
`e6f793eb6b6f54635ac5ca20974d295f435f2aa25b8b0aafb06e5a36a16ccd7a`.

`results/localnet-v2/summary.json`, `manifest.json`, and the 30 files under
`epochs/` are authoritative for this run. The public status remains **LOCALNET
EVIDENCE / TESTNET PENDING** because local evidence is not testnet evidence.

The acceptance command is intentionally stricter than signature verification
alone:

```bash
.bootstrap/bin/uv run python scripts/audit_localnet_v2.py results/localnet-v2
.bootstrap/bin/uv run planrace evidence verify results/localnet-v2/manifest.json
```

The auditor independently verifies every Bittensor HTTP request signature and
miner response signature, then recomputes the sandbox fixture scores, holdout
evaluations, observations, aggregate scores, headline scores, hotkey-to-UID
resolution, submitted vector, and readback. The official Subtensor image digest
is part of the signed manifest alongside the worker content ID.

The local evidence schedule is signed after the completed run. It is closed and
fully disclosed, but not externally timestamped in advance, so the bundle does
not exclude operator run-selection. Setup cost is measured once per fixture;
the confidence bound applies to repeated query timings conditional on that
observed setup. These limitations remain until an independently operated
testnet run.

The runner writes validator-only `run-input.json` and per-epoch checkpoints
under the operator-selected output directory after all task deadlines. A
stopped evaluation can continue with `--resume`. Those recovery files contain
secret task material and are intentionally excluded from the public bundle.
