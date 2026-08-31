# Incentive Mechanism

## Commodity

A PlanRace artifact is a versioned, canonical pair:

1. an SQL statement semantically equivalent to a supplied known-correct statement; and
2. zero or more bounded index definitions admitted by the track policy.

The artifact is executable and independently replayable. Prose advice, natural-language answers, and approximate result sets are not commodities in v1.

## Task lifecycle

1. **Commit:** validator publishes the task, limits, generator version, and `SHA256(protocol, task_id, seed, salt)`.
2. **Compete:** miners search without seeing hidden rows or distributions.
3. **Close:** submissions stop at the epoch deadline.
4. **Reveal:** validator reveals seed and salt; peers verify the commitment and regenerate rows.
5. **Gate:** every candidate must parse, stay within the SQL policy, finish within resource limits, and exactly match the reference canonical result.
6. **Rank:** correct artifacts compete on robust execution cost. Wrong artifacts receive exactly zero.
7. **Emit:** normalized positive epoch aggregates become weights; a later implementation will set them through the Bittensor SDK.

## Score v1

For a correct candidate:

```text
amortized_ms = median_warm_ms + setup_ms / expected_reuses
score = 100 / (1 + amortized_ms + explain_opcode_count / 1000)
```

`expected_reuses = 100` in the local prototype. The value will be part of a public track policy before testnet and cannot change within an epoch.

The formula deliberately uses no miner-reported time. Validators measure locally. The prototype reports plan complexity separately; production scoring will keep cold, warm, setup, memory, and robustness components observable rather than hiding them inside one timer.

## Gaming analysis

| Attack | v1 response | Remaining risk |
|---|---|---|
| Return fewer/approximate rows | Exact canonical hash → zero | Canonicalization must define numeric and NULL semantics per engine |
| Memorize public fixtures | Hidden committed seed and changing skew | Generator leakage or small curriculum |
| Multi-statement mutation | Admission rejection | Parser/grammar mismatch |
| Expensive denial query | Progress deadline and zero | In-process SQLite is not sufficient production isolation |
| Optimize only warm cache | Separate warm metric | Need cold/IO tracks and calibrated images |
| Index everything | Setup limit and amortized setup cost | Reuse assumption affects winner |
| Validator favors one strategy | Revealable generator and peer replay | Validator-written curricula remain governance power |
| Duplicate winner | Artifact hashing/deduplication planned | Attribution and incremental novelty need a policy |

## Weight policy (planned testnet)

- Aggregate per-task scores with fixed workload-family masses.
- Winsorize timing outliers only by a precommitted rule.
- Require a minimum number of correct tasks before a miner receives non-dust weight.
- Normalize eligible aggregates to the SDK's non-negative weight vector.
- Do not promise Sybil resistance until identity-splitting simulations and live observations support it.

## Buyer path

A buyer submits a query, sanitized schema, engine version, and statistics/distribution generator or private evaluation adapter. The returned artifact includes SQL, indexes, engine/version, result-evidence hashes, score components, and validator attestations. The initial hackathon demo uses generated data and makes no claim that customer data should be exposed to miners.
