# Protocol v2 localnet evidence

Status: **active evidence run; values below marked pending are not yet claims**.

## Topology

- Official Subtensor local development container, SDK Bittensor 11.1.0.
- Netuid 3, runtime spec 452 at setup.
- Three deterministic public development validator identities, all controlled by
  one operator on one machine.
- Ten deterministic public development miner identities with heterogeneous
  profiles: baseline, four useful optimization variants, hybrid, over-budget,
  constant-answer attempt, timeout/resource attempt, and copycat/Sybil.
- 30 closed-schedule epochs rotating the three validator identities.

These development identities use no valuable secret and must never be reused on
testnet or mainnet.

The profile named `restricted-rewrite` is intentionally narrowed to a structured
partial-index transformation in this track. Protocol v2 follows the brief's
first safety preference—fixed reference SQL plus structured index selection—and
does not pretend that raw or arbitrary rewrite safety has been established. The
constant-answer attempt likewise has no result field to exploit and collapses to
the no-index executable strategy; it is still distinguishable in the signed
response metadata but receives no special correctness shortcut.

## Local-chain preparation disclosure

The local runtime's development defaults prevented the required short test cycle
and its drand service was unavailable. Using the public local sudo identity only,
the operator set the local admin freeze window to zero and disabled runtime
commit/reveal on netuid 3. Protocol v2 still performs its own application-layer
task commitment, deadline, sealed submission set, and reveal. This exception is
local-only and is not evidence for a testnet configuration.

An isolated smoke submission succeeded before the full run: extrinsic
`2200-0002`, block
`0x705be2fca54e31cccfc5a93a0983a1dd2c434721e004a5424f7319b06b68b788`.
Its readback matched the submitted UID 3–12 test vector. This smoke vector was
hand-selected and is not the final mechanism-derived result.

## Full run

The authoritative command is:

```bash
.venv/bin/python -u scripts/run_localnet_v2.py \
  --epochs 30 --netuid 3 \
  --worker-image sha256:65decc96acf0f7e9895e73985eee947bacdd5dc5599c06b423191c90268170fa \
  --evaluation-workers 3
```

Expected evidence checks, not yet asserted as passed:

- exactly 30 epoch records and 300 signed validator requests;
- exactly nine accepted miner responses per epoch (the timeout profile is the
  sole intended transport failure);
- hidden reveal only after the final request deadline;
- seven unique strategy evaluations per epoch because two pairs intentionally
  duplicate artifacts and one profile is unavailable;
- exact mismatch/over-budget/timeout profiles receive no eligible reward;
- pairwise validator ranking correlation is reported, not assumed;
- the final mechanism-derived vector is actually submitted and read back;
- `manifest.json` verifies under the included validator signature and binds the
  summary plus all 30 epoch files by SHA-256.

When complete, `results/localnet-v2/summary.json`, `manifest.json`, and 30 files
under `epochs/` are authoritative. Until then, the public status is
**LOCALNET EVIDENCE / TESTNET PENDING**.

After the run, the acceptance command is intentionally stricter than signature
verification alone:

```bash
.venv/bin/python scripts/audit_localnet_v2.py \
  results/localnet-v2 --seal-source-artifacts
.venv/bin/python -m planrace evidence verify results/localnet-v2/manifest.json
```
