# Market Evidence

Checked: 2026-09-05. This document separates source facts from the PlanRace
product inference; it does not claim a fabricated market-size number.

## What the primary sources establish

Google Cloud's AlloyDB has a managed index advisor that tracks normalized
queries, periodically recommends indexes, and reports estimated storage and
query impact. Its Query Insights integration shows impacted tables, queries,
performance impact, and storage before a user chooses to create an index.
[Google Cloud: Index advisor overview](https://docs.cloud.google.com/alloydb/docs/index-advisor-overview)

Azure SQL automatic tuning continuously monitors workloads and supports
`CREATE INDEX`, `DROP INDEX`, and last-good-plan actions. Microsoft documents a
verification loop: changes are monitored and reverted when they do not produce
significant improvement or regress performance. Microsoft also notes that
indexes can speed reads while slowing updates, making index choice a measured
tradeoff rather than an always-add-more rule.
[Microsoft: Automatic database tuning](https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview)

AWS exposes SQL- and wait-level database-load data and performance analysis
through Database Insights / the Performance Insights API. Query digests group
literal variants, and detailed per-query metrics are available for RDS engines.
This establishes that cloud buyers already collect the workload signals needed
to define optimization challenges.
[AWS: Performance Insights API](https://docs.aws.amazon.com/performance-insights/latest/APIReference/Welcome.html) ·
[AWS: SQL statistics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/sql-statistics.html)

Bittensor's consensus design accepts validator weight vectors over miners, and
official research explicitly treats weight-copying/free-riding as an incentive
problem. This supports PlanRace's decision to deduplicate copied artifacts and
publish validator-owned evidence rather than trusting miner timings.
[Opentensor: consensus-based weights paper](https://docs.bittensor.com/papers/BT-Consensus-based-Weights.pdf)

## Product inference

The cloud products above prove demand for continuous query observation, index
recommendation, impact estimation, and post-change verification. They do not
prove that buyers will purchase decentralized query optimization. PlanRace's
testable wedge is narrower:

- a buyer or validator supplies an already-correct query and a safe synthetic
  workload specification;
- independent miners compete on bounded, reusable optimization artifacts;
- the validator substitutes exact hidden-fixture verification for vendor or
  miner trust;
- baseline-relative scoring prices setup, storage, reliability, and reuse;
- evidence can be audited without exposing production customer rows.

The plausible early buyer is a platform team with many repeated analytical or
application-query shapes, an existing synthetic/staging dataset process, and a
reason to compare approaches beyond one vendor's built-in advisor. PlanRace is
not yet evidence of production demand, data-governance approval, or willingness
to pay.

## Competitive boundary

Built-in cloud advisors have privileged telemetry, mature operational safety,
and direct integration. PlanRace should not claim to replace them. Its distinct
hypothesis is an open competition layer where heterogeneous optimizers can be
verified under one precommitted rule set and rewarded without sharing hidden
holdouts.

## Required comparison

| Alternative | What it already does well | Boundary versus PlanRace |
|---|---|---|
| Database-native query optimizer | Chooses an execution plan from engine statistics for every query. PostgreSQL `EXPLAIN` exposes the chosen scan and join plan and estimated cost. | It is one engine's planner, not a market in which independent solvers return portable, inspectable artifacts. PlanRace still executes the winning SQL/index artifact through the native optimizer. |
| PostgreSQL advisors and observability | `pg_stat_statements` tracks planning/execution statistics; `EXPLAIN (ANALYZE, BUFFERS)` supports empirical diagnosis. PostgreSQL documents that index selection often requires experimentation. | These are strong inputs and evaluation tools, but core PostgreSQL does not run an incentive market among independent optimizer implementations. A PostgreSQL adapter is future work. |
| Commercial database optimization services | Oracle SQL Tuning Advisor can recommend statistics, indexes, rewrites, profiles, and plan baselines; it has privileged database statistics and operational integration. | Mature vendor tooling has a major safety and context advantage. PlanRace's hypothesis is vendor-neutral competition plus a verifier-owned correctness/performance record, not superior privileged telemetry. |
| Automated index advisors | AlloyDB Index Advisor and Azure automatic tuning observe workloads and recommend or apply index changes with impact monitoring and rollback. | PlanRace admits bounded indexes but also prices setup/storage and allows heterogeneous search methods. It has not yet matched these products' operational safeguards. |
| Query benchmarking platforms | Repeatable benchmark harnesses compare engines/configurations and expose regressions. | PlanRace is not merely a leaderboard: each round produces an executable artifact, verifies it on hidden fixtures, aggregates repeated performance, and converts eligible value into subnet weights. |
| Existing Bittensor subnets | Bittensor supplies the miner/validator and weight-consensus substrate for competitive digital commodities. Official consensus research also identifies weight copying/free-riding as a live incentive issue. | PlanRace's commodity is neither model inference nor GPU capacity: it is a reusable query rewrite/index bundle whose result semantics can be replayed cheaply by validators. No claim is made that no similar subnet exists; a current on-chain category survey remains a pre-submission check. |
| Centralized solver API | A single service can protect customer data, tune against private telemetry, and provide a simple support boundary. | PlanRace adds solver diversity, transparent comparison, and independently replayable evidence, at the cost of greater coordination and evaluation overhead. A private-data adapter is not implemented. |

Sources: [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html),
[PostgreSQL index examination](https://www.postgresql.org/docs/current/indexes-examine.html),
[PostgreSQL `pg_stat_statements`](https://www.postgresql.org/docs/current/pgstatstatements.html),
[Oracle SQL Tuning Advisor](https://docs.oracle.com/en/database/oracle/oracle-database/18/tgsql/sql-tuning-advisor.html),
[Google AlloyDB Index Advisor](https://docs.cloud.google.com/alloydb/docs/index-advisor-overview),
[Azure automatic tuning](https://learn.microsoft.com/en-us/azure/azure-sql/database/automatic-tuning-overview), and
[Opentensor consensus-based weights](https://docs.bittensor.com/papers/BT-Consensus-based-Weights.pdf).

## What PlanRace is—and is not

PlanRace is **not** natural-language-to-SQL, a query-answer subnet, a GPU
marketplace, or a benchmark leaderboard. It is a proposed recurring market in
which independent optimizers produce executable artifacts, validators verify
correctness and measured value on behalf of a buyer, and the buyer can replay
and audit the winning artifact. Demand can recur as schemas, data distributions,
workloads, and engine releases change.

## Three concrete buyer workflows

### 1. Database-release regression

A platform team detects that a known-correct query shape regressed after an
engine upgrade. Its private adapter (future work) exports a sanitized schema,
parameter distribution, and synthetic generator rather than customer rows. The
validator commits hidden fixtures; miners propose bounded artifacts; the team
receives the exact-passing winner, setup/storage tradeoffs, and a replayable
manifest to compare against its release baseline.

### 2. SaaS query-cost reduction

A multi-tenant SaaS operator groups a repeated high-cost query into a normalized
shape and defines representative safe distributions and reuse horizons. Miners
compete on index and approved rewrite strategies. The validator rejects
result-changing or unavailable submissions, prices index construction and
storage, and returns a candidate the operator can stage and audit before any
production rollout.

### 3. Analytical-pipeline optimization

A data team schedules a recurring challenge for stable transformations whose
volume and skew change weekly. Independent solvers may use rules, search, or
learned methods. Hidden holdouts include skew and boundary cases; the winner is
selected by correctness first and robust latency/cost second. A DuckDB or
PostgreSQL analytical track and production data connector are future work; the
current proof uses generated SQLite workloads only.

## Validation still required

1. Interview database/platform teams about acceptable synthetic workload
   disclosure and the minimum useful artifact scope.
2. Measure whether third-party strategies beat a strong built-in/reference
   advisor after setup and storage cost.
3. Test PostgreSQL or another production engine; current evidence is SQLite.
4. Quantify validator cost versus miner search cost on representative workloads.
5. Obtain testnet evidence before asserting decentralized operation.
