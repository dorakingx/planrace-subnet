# Scoring

The validator first executes the reference query and hashes canonical result
rows. Candidate output must have the same hash. Admission failure, timeout, SQL
error, task mismatch, or result mismatch scores zero.

For a correct artifact:

```text
amortized_ms = median(warm repetitions) + setup_ms / 100
score = 100 / (1 + amortized_ms + plan_instruction_count / 1000)
```

Measurements occur on the validator, never on miner-reported timing. Tracks and
hardware must be calibrated separately; v1 does not compare unlike engines.
