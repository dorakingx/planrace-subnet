# Security

## Implemented

- exact-byte receiver-bound Bittensor HTTP authentication;
- persistent nonce replay rejection and freshness checks;
- strict immutable message models with unknown fields forbidden;
- bounded request bodies, SQL size, setup count, and query execution time;
- read-only single-statement candidate admission and index-only setup;
- no secrets or real data in fixtures; CI secret scan and dependency audit.

## Production boundary

In-process SQLite is a mechanism prototype, not a hostile-code sandbox.
Production validators must use disposable workers with filesystem, syscall,
memory, CPU, and wall-clock limits. Report vulnerabilities privately to the
repository owner; do not include wallet seeds or live exploit data in issues.
