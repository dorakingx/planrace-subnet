# Architecture

## Protocol v2 executable slice

```text
taskgen_v2.py ── public commitment + private reveal ───────┐
                                                           │
auth_v2.py ─ signed request/response + replay ─ api_v2.py ─┤
                                                           ▼
models_v2.py ─ structured bundle ─ sandbox_v2.py ─ Docker worker
                                                           │
benchmark_v2.py ─ hidden fixtures ─ oracle_v2.py ──────────┤
                                                           ▼
evaluation_v2.py ─ exact gate + paired measurements ─ scoring_v2.py
                                                           │
                                                           ▼
                                      multi-epoch allocation + evidence + chain
```

- `models_v2.py`: strict immutable wire objects, structured `IndexSpec`, and
  canonical domain-separated digests.
- `taskgen_v2.py` / `benchmark_v2.py`: opaque CSPRNG task construction,
  commitment/reveal audit, families, and hidden fixture generation.
- `auth_v2.py`, `api_v2.py`, `validator_client_v2.py`: receiver-bound request
  auth, miner-signed responses, expiry, and replay controls.
- `sandbox_v2.py` / `sandbox_worker.py`: isolated batch orchestration,
  validator-compiled artifacts, exact execution evidence, and bounded failures.
- `evaluation_v2.py` / `scoring_v2.py`: exact-first evaluation,
  baseline-relative fixture reward, robust aggregation, duplicate handling, and
  weight planning.
- Unsuffixed modules preserve the historical protocol v1 path.

## Bittensor data plane

Bittensor v11 removed the historical application networking stack, so PlanRace
owns its FastAPI/httpx data plane and uses `bittensor.http_auth.sign/verify` for
receiver-bound request authentication. Protocol v2 adds its own signed miner
response envelope. `ServeAxon` publishes endpoint metadata; it is not the HTTP
server. Historical v1 is in [LOCALNET.md](LOCALNET.md); the ten-miner v2 run is
tracked in [LOCALNET_V2.md](LOCALNET_V2.md).

```text
subtensor local/test
  ├─ metagraph / registration / ServeAxon / set_weights
  └─ validator discovers miner endpoint
       └─ signed HTTP PublicTaskV2
            └─ miner FastAPI → SignedOptimizationResponse
                 └─ validator disposable DB workers → exact evidence
                      └─ robust multi-epoch allocation → chain + manifest
```

## Validator trust boundary

Validators know generated rows after independently choosing secret material.
Commit/reveal proves they did not change it after submissions; it does not prove
the curriculum is unbiased. The current closed schedule and fixed family masses
reduce discretion, while independent operators, peer replay, and future entropy
mixing remain necessary.

## Planned tracks

1. SQLite generated orders (current mechanism proof).
2. DuckDB analytical queries with Parquet fixtures.
3. PostgreSQL pinned container with EXPLAIN ANALYZE and parameter distributions.
4. Buyer-provided private adapters that reveal only attestations/artifacts, subject to a separate privacy design.

Tracks never compare raw latency across unlike engines or machines.
