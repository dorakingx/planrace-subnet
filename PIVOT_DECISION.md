# Pivot Decision

**Decision:** pivot from QECForge to PlanRace and use a new repository (Option B).

PlanRace ranked 3rd of 27 hard-gate survivors in the blind equal-weight pass and placed 3rd/4th/5th under equal, mechanism-heavy, and market-heavy scenarios. QECForge ranked 12th/9th/16th. After red-team and spikes, PlanRace became the highest-confidence build because it combines an exact semantic gate, a recurring infrastructure market, a short live demo, and a deadline-safe implementation.

The isolated PlanRace spike:

- kept exact reference hashes across all honest runs;
- rejected the fast semantically widened query with score zero;
- beat the unoptimized exact baseline in 20/20 repeated five-epoch runs;
- produced a mean honest/baseline score ratio of 1.663 (observed 1.640–1.682).

Maximum risks are cross-validator timing comparability, overlap perception with QueryAgent/database-native advisors, synthetic-to-production transfer, untrusted SQL isolation, and buyer workload privacy.

The choice is frozen unless testnet reveals one fundamental failure: independent validators cannot reproduce correct relative rankings under the calibrated protocol.

Full score tables, market evidence, red-team attacks, and rejected candidates are preserved in the [historical pivot record](https://github.com/dorakingx/qecforge-subnet/blob/main/PIVOT_DECISION.md).
