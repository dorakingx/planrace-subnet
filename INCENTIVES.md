# Incentives v2

Weights reward a lower-confidence, baseline-relative saving measured on the
validator—not a miner's claimed runtime and not an absolute millisecond score.
Exact result equality and policy compliance are hard gates. Cold/warm execution,
setup, storage, four reuse horizons, and timeouts are all priced explicitly.

Across epochs, fixed workload-family mass, downside uncertainty, availability,
and compliance prevent one lucky or cherry-picked task from determining weight.
Canonical duplicate strategies share one fixed reward pool and allocation, so
identity cloning does not add strategy reward. A 25% observed-behavior cap and
reported Gini, HHI, and top-one share make concentration observable and bounded
under the current policy. Gate failures produce no new update; any previously
stored chain vector may persist until replaced or aged out.

These are mechanism rules, not a claim of solved real-world Sybil resistance.
The deterministic evidence in `results/mechanism-v2/` exercises duplicate
identities and validator attacks; testnet observations are still required.
