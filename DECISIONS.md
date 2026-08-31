# Decisions

| Date | Decision | Reason |
|---|---|---|
| 2026-08-31 | Select PlanRace after a zero-base 42-idea review | It combines cheap exact verification, recurring demand, and a legible live demo. |
| 2026-08-31 | Use a new `dorakingx/planrace-subnet` repository | The pivot is material; preserving QECForge history would confuse evaluation. |
| 2026-08-31 | Make correctness a hard gate | A fast wrong query is not a useful commodity. |
| 2026-08-31 | Own HTTP transport with Bittensor v11 auth | Current SDK publishes endpoints but does not provide the former application RPC stack. |
| 2026-08-31 | Restrict v1 to generated SQLite workloads | A narrow, replayable track is more defensible than uncalibrated cross-engine benchmarks. |

Decisions never used founder-market fit, prior chats, or existing code quantity as selection criteria.
