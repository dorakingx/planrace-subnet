# Security

## Implemented

- exact-byte receiver-bound Bittensor HTTP request authentication;
- domain-separated miner sr25519 response signatures bound to request, task,
  receiver, artifact, timestamps, and nonce;
- bounded persistent/memory nonce replay rejection and freshness checks in both
  directions;
- strict immutable message models with unknown fields forbidden;
- bounded request/response envelopes, SQL size, structured index count, and
  query execution time;
- one read-only allowlisted SELECT and validator-compiled `IndexSpec` DDL;
- independent OS-CSPRNG seed and salt, opaque public task ID, committed hidden
  fixture Merkle root, sealed deadline, and post-deadline reveal audit;
- disposable non-root Docker workers with no network, read-only root,
  capability drop, no-new-privileges, PID/file/CPU/memory/wall-clock limits, and
  throwaway writable tmpfs;
- worker timeout, crash, malformed output, oversize output, and OOM are mapped to
  bounded failure observations instead of stopping the validator;
- no secrets or real data in fixtures; CI secret scan and dependency audit.

## Honest boundary

Docker isolation materially improves the prototype but is not a formal sandbox
escape proof. The worker image is locally content-addressed for localnet; a
published registry digest, SBOM/signature policy, host hardening, and independent
security review remain required. SQLite and conservative parsing do not establish
arbitrary SQL safety or universal equivalence. Raw SQL scope must narrow to
structured indexes/approved AST transformations if the stated kill gates fail.

Report vulnerabilities privately to the repository owner; do not include wallet
seeds, customer queries, live exploit data, or private infrastructure details in
public issues.
