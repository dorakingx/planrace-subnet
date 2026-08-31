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
- Candidate admission permits one SELECT/WITH statement; setup admits only bounded indexes on named tables.
- Commit/reveal makes post-submission seed switching detectable.
- Exact result hashing precedes all performance reward.
- SQLite progress handlers bound instruction time in the prototype.
- Generated fixtures contain no customer data.

The current process is **not** a hardened sandbox. SQL parsing is conservative text admission rather than an AST whitelist, execution is in-process, and wall-clock measurements are local. Before a public miner endpoint, run each candidate in a disposable container/VM with CPU, memory, filesystem, syscall, and network limits; use a real parser; and discard the worker after every task.

## Chain safety

Only `local` and `test` targets will be accepted. Mainnet aliases and arbitrary RPC URLs must fail closed. Wallet seed phrases are never logged or committed. Registration, faucet/test TAO, and signatures that require the user's wallet remain explicit user actions.

## Responsible disclosure

Security issues should be reported privately to the repository owner. Do not include live credentials, customer queries, or exploitable private infrastructure details in issues.
