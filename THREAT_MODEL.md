# Threat Model

## Protected properties

- semantic correctness of rewarded artifacts;
- integrity and freshness of validator tasks;
- reproducibility of score evidence;
- availability of validator workers;
- miner/validator hotkeys and signing material;
- absence of private buyer data in public artifacts.

## Adversaries

- malicious miner submitting SQL/DDL intended to escape, mutate, exhaust, or fingerprint;
- gaming miner optimizing exposed fixtures instead of the commodity;
- dishonest validator choosing biased tasks or fabricating scores;
- replay attacker resending authenticated requests;
- Sybil operator splitting one strategy across hotkeys;
- external observer inferring private workload details.

## Current controls and honest limits

- Strict Pydantic models forbid extra fields and bound payloads.
- Candidate admission permits one allowlisted SELECT; setup is a structured
  index AST compiled by the validator and checked against task schema/budget.
- Independent seed/salt commitment and hidden descriptor root make
  post-submission switching detectable; the public task does not contain the
  seed, salt, or a deterministic derivation of either.
- Receiver-bound requests and miner-signed responses cover identity, task,
  artifact, nonce, and freshness; replay stores reject reuse.
- Exact result hashing precedes all performance reward.
- Candidate/reference execution is isolated in a disposable, network-disabled,
  non-root Docker worker with a read-only root, throwaway tmpfs, dropped
  capabilities, no-new-privileges, and PID/file/CPU/memory/wall limits.
- The worker additionally applies SQLite query deadlines and bounded canonical
  result/output envelopes. Worker failure becomes unavailable/zero.
- Duplicate executable strategies reuse one task evaluation and split/recombine
  portfolio mass; this removes direct copy amplification but not general Sybil
  or collusion.
- Generated fixtures contain no customer data.

The container boundary is not a formal proof against a kernel/runtime escape.
The current engine and measurement evidence are local SQLite. Future-block
entropy mixing, a public signed worker image, independent validator operators,
production-engine semantics, and privacy-preserving buyer adapters remain open.
Commit/reveal proves consistency with chosen material, not an unbiased curriculum.
Exact finite fixtures do not prove universal SQL equivalence.

## Chain safety

Only `local` and `test` targets will be accepted. Mainnet aliases and arbitrary RPC URLs must fail closed. Wallet seed phrases are never logged or committed. Registration, test-TAO allocation, and signatures that require the user's wallet remain explicit user actions.

## Responsible disclosure

Security issues should be reported privately to the repository owner. Do not include live credentials, customer queries, or exploitable private infrastructure details in issues.
