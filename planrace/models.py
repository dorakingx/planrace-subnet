"""Strict wire and scoring models for the PlanRace v1 commodity."""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

PROTOCOL_VERSION: Final = "planrace/1"
MAX_SQL_BYTES: Final = 64 * 1024
MAX_SETUP_STATEMENTS: Final = 4

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
]
SqlText = Annotated[str, StringConstraints(min_length=1, max_length=MAX_SQL_BYTES)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class QueryTask(StrictModel):
    protocol_version: Literal["planrace/1"] = PROTOCOL_VERSION
    task_id: Identifier
    epoch: Annotated[int, Field(ge=0)]
    engine: Literal["sqlite-3"]
    schema_sql: SqlText
    reference_sql: SqlText
    generator_version: Literal["orders-v1"]
    seed_commitment: Sha256Hex
    max_setup_statements: Annotated[int, Field(ge=0, le=MAX_SETUP_STATEMENTS)] = 2
    repetitions: Annotated[int, Field(ge=3, le=25)] = 7


class OptimizationArtifact(StrictModel):
    protocol_version: Literal["planrace/1"] = PROTOCOL_VERSION
    task_id: Identifier
    miner_id: Identifier
    strategy: Identifier
    candidate_sql: SqlText
    setup_sql: tuple[SqlText, ...] = ()

    @field_validator("setup_sql")
    @classmethod
    def limit_setup(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > MAX_SETUP_STATEMENTS:
            raise ValueError("too many setup statements")
        return value


class ScoreBreakdown(StrictModel):
    task_id: Identifier
    miner_id: Identifier
    correct: bool
    score: Annotated[float, Field(ge=0.0)]
    result_hash: Sha256Hex | None
    reference_hash: Sha256Hex
    plan_cost: Annotated[int, Field(ge=0)]
    median_warm_ms: Annotated[float, Field(ge=0.0)]
    setup_ms: Annotated[float, Field(ge=0.0)]
    failure_code: Identifier | None


class SeedReveal(StrictModel):
    task_id: Identifier
    seed: Annotated[int, Field(ge=0, le=2**63 - 1)]
    salt: Identifier
