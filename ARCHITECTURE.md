# Architecture

## Current executable slice

```text
taskgen.py ── QueryTask + hidden workload ──┐
                                            │
miners.py ── OptimizationArtifact ──────────┼─ scoring.py ─ ScoreBreakdown
                                            │
sandbox.py ─ admission + deadline ─────────┘
                         │
simulation.py ─ multiple epochs + ranking
```

- `models.py`: strict immutable versioned wire objects.
- `taskgen.py`: deterministic hidden workload, seed commitment, and reveal verification.
- `miners.py`: reference strategies only; the protocol does not require their implementation.
- `sandbox.py`: narrow SQL/DDL admission and query progress deadline.
- `scoring.py`: reference execution, canonical hash, hard gate, and measured score.
- `simulation.py`: epoch orchestration independent of a chain.

## Bittensor data plane

Bittensor v11 removed the historical application networking stack, so PlanRace owns its FastAPI/httpx data plane and uses `bittensor.http_auth.sign/verify` for receiver-bound request authentication. `ServeAxon` publishes endpoint metadata; it is not the HTTP server. This path has been exercised against registered localnet neurons; see [LOCALNET.md](LOCALNET.md).

```text
subtensor local/test
  ├─ metagraph / registration / ServeAxon / set_weights
  └─ validator discovers miner endpoint
       └─ signed HTTP QueryTask
            └─ miner FastAPI → OptimizationArtifact
                 └─ validator disposable DB worker → ScoreBreakdown
```

## Validator trust boundary

Validators know generated rows after they choose a seed. Commit/reveal proves they did not change that seed after submissions; it does not prove the curriculum is unbiased. Production needs independently generated tasks, fixed workload-family masses, peer replay, and public score artifacts.

## Planned tracks

1. SQLite generated orders (current mechanism proof).
2. DuckDB analytical queries with Parquet fixtures.
3. PostgreSQL pinned container with EXPLAIN ANALYZE and parameter distributions.
4. Buyer-provided private adapters that reveal only attestations/artifacts, subject to a separate privacy design.

Tracks never compare raw latency across unlike engines or machines.
