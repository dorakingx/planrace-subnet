# Submission copy

## Name

PlanRace

## Tagline

The competitive market for verified query plans.

## Short description

PlanRace is a Bittensor subnet where miners produce faster SQL rewrites and
bounded index plans. Validators replay artifacts on unrevealed generated test
databases, require exact result equality, measure performance themselves,
and convert only correct scores into weights. It makes optimization open to
competing solvers while keeping verification cheap, objective, and reproducible.

The published epoch-8 evidence is historical protocol v1 localnet evidence. Its
deterministic task ID leaked the fixture seed, responses were unsigned, and no
testnet result is claimed; these limits are carried in the signed manifest.

## Users and roadmap

Database teams, engine vendors, and data platforms need recurring optimization
as workloads and releases change. After the SQLite mechanism proof: testnet
multi-miner operation, disposable workers, DuckDB analytical tasks, PostgreSQL
parameter distributions, independent validators, and buyer-provided workloads.
