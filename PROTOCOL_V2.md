# PlanRace Protocol v2

Status: implemented for localnet evidence. Testnet deployment is pending.

## Commodity

A miner produces a reusable optimization artifact for a validator-owned,
already-correct SQL query. Protocol v2 accepts only a bounded structured index
AST. It does not accept query answers, raw SQL rewrites, arbitrary DDL, code,
timings, or miner-selected index names.

## Task lifecycle

1. The validator draws an opaque 128-bit `task_id`, a 256-bit secret seed, and
   an independent 256-bit salt from the operating-system CSPRNG.
2. The secret seed deterministically expands into eight private fixture
   descriptors. Their ordered Merkle root, generator digest, benchmark-policy
   digest, public training fixture, query family, schema, reference query,
   artifact budget, deadline, seed, and salt are bound by the task commitment.
3. Before the deadline, miners receive only `PublicTaskV2`. It exposes a
   separately seeded training fixture, parameter ranges, and coarse statistics;
   neither the secret seed nor concrete holdout contents are public.
4. A receiver-bound, validator-signed HTTP request carries one opaque request
   ID and nonce to one registered miner hotkey.
5. The miner returns `SignedOptimizationResponse`. Its sr25519 signature binds
   both hotkeys, request digest, request ID, nonce, task ID, artifact digest,
   and validity interval.
6. The lifecycle seals submissions at the deadline before exposing
   `TaskRevealV2`. Regenerated fixture descriptors and the Merkle root must
   match the original commitment.
7. A disposable worker validates the fixture, task, policy, engine, artifact,
   exact result, and relative performance. Only worker-authored evidence can
   reach scoring.
8. Task rewards are deduplicated by executable strategy, aggregated over a
   closed multi-family schedule, concentration-capped, and converted to chain
   weights. Invalid benchmark evidence produces no update.

## Artifact grammar

`OptimizationBundle` contains at most the task's declared number of
`IndexSpec` values. Each index has a validated table, ordered key columns,
optional covering columns, optional bounded conjunction of tagged predicates,
and an optional uniqueness flag. Identifiers use a strict ASCII grammar.
Predicate values are tagged integer, text, boolean, or null literals.

The validator derives every index name and compiles the AST. Raw miner strings
never become executable SQL. SQLite authorizer rules, schema fingerprints,
parser/function allowlists, byte limits, query deadlines, database growth
limits, and result limits provide independent defense in depth.

## Authentication and replay boundary

The validator checks the expected UID-to-hotkey mapping before accepting a
response. Verification then checks the miner signature, both receivers, task,
request, nonce, request digest, artifact digest, expiry, and replay store.
Response time is sampled only after the bounded body stream is complete.
Redirects, ambient proxies, credential-bearing URLs, invalid/duplicate framing
headers, non-JSON success bodies, private/reserved production endpoints, and
oversized bodies fail closed.

Localhost is enabled only by an explicit test flag. Production callers must use
an `httpx.AsyncClient` with `trust_env=False` and no proxy mounts.

## Exact-first evaluation

Each candidate and the reference query execute against the same committed
fixture and parameters. Ordered results preserve row order; scalar types,
NULLs, integers, text, blobs, and bounded floats have canonical encodings.
Result row, cell, and byte limits apply while streaming. A mismatch, timeout,
invalid baseline, mixed worker identity, or policy mismatch cannot earn reward.

## Known limitation: future-block entropy

The implemented task seed is independent OS-CSPRNG entropy with a post-deadline
reveal. It is not yet mixed with a predeclared future testnet block hash.
Adding that mechanism before a stable testnet chain adapter would create
ambiguous reorg, block-selection, and reveal rules. Testnet remains blocked
until those rules are specified or the limitation is explicitly accepted; no
claim of validator-grinding resistance is made today.

## Version separation

`planrace/1` remains only for replaying historical localnet evidence. New tasks,
responses, commitments, strategy digests, worker evidence, and scores use
domain-separated `planrace/2:*` encodings. A v1 artifact is not a v2 artifact.

