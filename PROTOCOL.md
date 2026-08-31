# Protocol v1

`QueryTask` contains protocol version, task/epoch IDs, pinned engine, schema,
known-correct SQL, generator version, a seed commitment, setup limits, and
repetitions. `OptimizationArtifact` contains the task/miner IDs, candidate SQL,
strategy, and bounded setup DDL. `ScoreBreakdown` records hashes, correctness,
timings, plan cost, score, and a machine-readable failure.

The validator signs exact request bytes with `bittensor.http_auth.sign`; the
miner verifies method, raw target, body, receiver, timestamp, nonce, signature,
and validator authorization before parsing JSON. Responses with mismatched task
or miner identity are rejected. Schema definitions live in
[`planrace/models.py`](planrace/models.py); auth is in
[`planrace/auth.py`](planrace/auth.py).
