# Evidence index

This index separates historical protocol v1, current protocol v2 simulation,
localnet, and future testnet evidence. A missing artifact is marked pending.

## Reproduce and verify

```bash
make bootstrap
make sync
make verify
.bootstrap/bin/uv run python scripts/verify_mechanism_v2.py --require-clean-source
.bootstrap/bin/uv run planrace evidence verify results/localnet-v2/manifest.json
.bootstrap/bin/uv run python scripts/audit_localnet_v2.py results/localnet-v2
```

The localnet manifest is signed by an externally expected but publicly
derivable development signer, so it is a tamper-evident checksum rather than
independent-operator authenticity. The deterministic mechanism manifest is a
seed/source/lock/artifact hash ledger. Neither form makes a localnet or
simulation run a testnet run.

## Protocol v2 security and mechanism

| Claim | Human-readable specification | Code | Tests | Machine evidence |
|---|---|---|---|---|
| Hidden commitment and post-deadline reveal | `PROTOCOL_V2.md`, `BENCHMARK_POLICY.md` | `planrace/taskgen_v2.py`, `benchmark_v2.py` | `tests/test_benchmark_v2.py`, `test_protocol_v2.py` | 30 localnet epoch `task_public` / `task_reveal` records |
| Signed request and response; replay rejection | `PROTOCOL_V2.md`, `SECURITY.md` | `planrace/auth_v2.py`, `api_v2.py`, `validator_client_v2.py` | `tests/test_auth_v2.py` | 300 request digests and 270 response digests in the v2 manifest |
| Exact-result oracle | `SCORING.md` | `planrace/oracle_v2.py`, `evaluation_v2.py` | `tests/test_oracle_v2.py`, `test_evaluation_v2.py` | Per-fixture hashes in 30 epoch records |
| Worker isolation and failure containment | `BENCHMARK_POLICY.md`, `THREAT_MODEL.md` | `planrace/sandbox_v2.py`, `sandbox_worker.py` | `tests/test_sandbox_v2.py` | Worker status/failure codes in 30 epoch records |
| Robust multi-epoch scoring | `SCORING.md`, `MECHANISM_SIMULATION.md` | `planrace/scoring_v2.py` | `tests/test_scoring_v2.py` | `results/mechanism-v2/summary.json`, `replications.csv` |

## Network evidence

- Historical v1: `LOCALNET.md`, `results/localnet-epoch-8.json`.
- Protocol v2 localnet: `LOCALNET_V2.md` and
  `results/localnet-v2/{summary,manifest}.json` plus `epochs/`.
- Protocol v2 testnet: **pending**; see `TESTNET.md`.

## Product, market, and deployment

- `MARKET_EVIDENCE.md`: official-source facts, product inference, comparison,
  and three buyer workflows.
- `UPDATED_SUBNET_PROPOSAL.md`: commodity, roles, mechanism, safety, roadmap.
- `JUDGING_MATRIX.md`: claim-to-artifact mapping and explicit gaps.
- `CHECKPOINT_REVIEW.md`: six-role pre-checkpoint/final review worksheet and
  current blockers.
- `DEPLOYMENT_PROVENANCE.md`: GitHub/Vercel identity and public checks.
- `CHECKPOINT_PROPOSAL.md` and `SUBMISSION_COPY.md`: drafts only until gates pass.

## Integrity boundaries

- OS-CSPRNG makes the current local generator unpredictable from its public task,
  but future-block entropy mixing is not implemented.
- Three validator identities on localnet are controlled by one operator.
- The local worker image is an immutable Docker content ID, not a public image.
- Generated SQLite evidence is neither customer data nor a PostgreSQL result.
- The dashboard must render the committed manifest; it must not invent values.
