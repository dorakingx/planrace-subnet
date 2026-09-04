"""Strict, non-SQL wire models for the PlanRace v2 protocol.

Version 1 remains in :mod:`planrace.models`.  Nothing in this module changes
the historical v1 wire format or evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

PROTOCOL_VERSION_V2: Final = "planrace/2"
COMMITMENT_DOMAIN_V2: Final = "planrace/2:task-commitment"
ARTIFACT_DOMAIN_V2: Final = "planrace/2:optimization-bundle"
STRATEGY_DOMAIN_V2: Final = "planrace/2:executable-strategy"
REQUEST_DOMAIN_V2: Final = "planrace/2:optimization-request"
RESPONSE_DOMAIN_V2: Final = "planrace/2:optimization-response"

MAX_INDEXES_V2: Final = 4
MAX_COLUMNS_PER_INDEX_V2: Final = 8
MAX_PREDICATES_V2: Final = 8
MAX_PUBLIC_SQL_BYTES_V2: Final = 64 * 1024

Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
OpaqueId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
Hotkey = Annotated[
    str,
    StringConstraints(min_length=32, max_length=64, pattern=r"^[1-9A-HJ-NP-Za-km-z]+$"),
]
SqlTextV2 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MAX_PUBLIC_SQL_BYTES_V2),
]
SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=63, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
]
BenchmarkFamilyId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$"),
]
Hex32Bytes = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SignatureHex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{128}$")]


class StrictV2Model(BaseModel):
    """A stable wire model: strict inputs, no unknown fields, immutable values."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def canonical_json_bytes(value: BaseModel | Mapping[str, Any] | Sequence[Any]) -> bytes:
    """Return the one canonical JSON representation used by all v2 digests.

    Floats are intentionally forbidden.  Protocol quantities that need a
    fraction use integer basis points, preventing cross-runtime float drift.
    """

    if isinstance(value, BaseModel):
        raw: Any = value.model_dump(mode="json")
    else:
        raw = value
    _assert_canonical_value(raw)
    return json.dumps(
        raw,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def domain_separated_digest(
    domain: str, value: BaseModel | Mapping[str, Any] | Sequence[Any]
) -> str:
    """Hash a length-delimited canonical payload in an explicit v2 domain."""

    if not domain.startswith("planrace/2:"):
        raise ValueError("v2 digest domain must start with 'planrace/2:'")
    payload = canonical_json_bytes(value)
    prefix = domain.encode("ascii")
    framed = len(prefix).to_bytes(2, "big") + prefix + len(payload).to_bytes(8, "big") + payload
    return "sha256:" + hashlib.sha256(framed).hexdigest()


def _assert_canonical_value(value: Any) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        raise TypeError("floats are not permitted in PlanRace v2 canonical payloads")
    if isinstance(value, list | tuple):
        for item in value:
            _assert_canonical_value(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical object keys must be strings")
            _assert_canonical_value(item)
        return
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


class IntegerLiteral(StrictV2Model):
    kind: Literal["integer"] = "integer"
    value: int


class TextLiteral(StrictV2Model):
    kind: Literal["text"] = "text"
    value: Annotated[str, StringConstraints(max_length=256)]


class BooleanLiteral(StrictV2Model):
    kind: Literal["boolean"] = "boolean"
    value: bool


class NullLiteral(StrictV2Model):
    kind: Literal["null"] = "null"


type PredicateLiteral = Annotated[
    IntegerLiteral | TextLiteral | BooleanLiteral | NullLiteral,
    Field(discriminator="kind"),
]


class PredicateAtom(StrictV2Model):
    """A deliberately small partial-index predicate language."""

    column: SafeIdentifier
    operator: Literal["eq", "ne", "lt", "lte", "gt", "gte", "is_null", "is_not_null"]
    value: PredicateLiteral = Field(default_factory=NullLiteral)

    @model_validator(mode="after")
    def validate_null_operator(self) -> PredicateAtom:
        is_null_literal = isinstance(self.value, NullLiteral)
        is_null_operator = self.operator in {"is_null", "is_not_null"}
        if is_null_literal != is_null_operator:
            raise ValueError("NULL literals are only valid with IS NULL operators")
        return self


class PredicateExpression(StrictV2Model):
    """A bounded conjunction; no raw expressions, functions, OR, or subqueries."""

    conjunction: Literal["and"] = "and"
    atoms: Annotated[tuple[PredicateAtom, ...], Field(min_length=1, max_length=MAX_PREDICATES_V2)]


class IndexColumn(StrictV2Model):
    column: SafeIdentifier
    direction: Literal["asc", "desc"] = "asc"


class IndexSpec(StrictV2Model):
    """Miner-selected index structure without a name or executable SQL.

    SQLite has no separate ``INCLUDE`` clause, so ``include_columns`` are
    compiled as covering tail key columns.  They are prohibited on unique
    indexes because otherwise they would silently widen uniqueness semantics.
    """

    table: SafeIdentifier
    key_columns: Annotated[
        tuple[IndexColumn, ...], Field(min_length=1, max_length=MAX_COLUMNS_PER_INDEX_V2)
    ]
    include_columns: Annotated[
        tuple[SafeIdentifier, ...], Field(max_length=MAX_COLUMNS_PER_INDEX_V2)
    ] = ()
    unique: bool = False
    predicate: PredicateExpression | None = None

    @model_validator(mode="after")
    def reject_duplicate_columns(self) -> IndexSpec:
        names = [item.column for item in self.key_columns] + list(self.include_columns)
        if len(names) != len(set(names)):
            raise ValueError("an index may not repeat a column")
        if self.unique and self.include_columns:
            raise ValueError("unique indexes cannot contain SQLite covering tail columns")
        return self


class BundleMetadata(StrictV2Model):
    strategy: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    estimated_intent: Literal[
        "filter", "join", "order", "group", "covering", "mixed", "no_index"
    ]
    rationale: Annotated[str, StringConstraints(max_length=512)] = ""


class OptimizationBundle(StrictV2Model):
    """The only v2 miner artifact accepted by a validator."""

    protocol_version: Literal["planrace/2"] = PROTOCOL_VERSION_V2
    task_id: OpaqueId
    engine_image_digest: Sha256Digest
    indexes: Annotated[tuple[IndexSpec, ...], Field(max_length=MAX_INDEXES_V2)] = ()
    metadata: BundleMetadata
    artifact_digest: Sha256Digest

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        engine_image_digest: str,
        indexes: tuple[IndexSpec, ...],
        metadata: BundleMetadata,
    ) -> OptimizationBundle:
        payload = {
            "protocol_version": PROTOCOL_VERSION_V2,
            "task_id": task_id,
            "engine_image_digest": engine_image_digest,
            "indexes": [item.model_dump(mode="json") for item in indexes],
            "metadata": metadata.model_dump(mode="json"),
        }
        return cls(
            task_id=task_id,
            engine_image_digest=engine_image_digest,
            indexes=indexes,
            metadata=metadata,
            artifact_digest=domain_separated_digest(ARTIFACT_DOMAIN_V2, payload),
        )

    @model_validator(mode="after")
    def verify_artifact_digest(self) -> OptimizationBundle:
        if self.artifact_digest != optimization_bundle_digest(self):
            raise ValueError("artifact_digest does not match bundle contents")
        return self


def optimization_bundle_digest(bundle: OptimizationBundle) -> str:
    payload = bundle.model_dump(mode="json", exclude={"artifact_digest"})
    return domain_separated_digest(ARTIFACT_DOMAIN_V2, payload)


def optimization_strategy_digest(bundle: OptimizationBundle) -> str:
    """Hash only executable strategy semantics for duplicate/Sybil grouping.

    Task IDs and descriptive miner metadata are deliberately excluded.  In the
    v2 structured-index track the reference query is validator-owned, so the
    executable contribution is exactly the ordered index AST plus its engine.
    Cosmetic rationale or strategy-label changes therefore cannot evade
    duplicate reward splitting.
    """

    normalized_indexes: list[dict[str, Any]] = []
    for index in bundle.indexes:
        normalized = index.model_dump(mode="json")
        predicate = normalized.get("predicate")
        if predicate is not None:
            # AND is commutative.  Sort atoms by their canonical encoding while
            # preserving key-column order, which is executable index semantics.
            predicate["atoms"] = sorted(
                predicate["atoms"], key=lambda atom: canonical_json_bytes(atom)
            )
        normalized_indexes.append(normalized)
    normalized_indexes.sort(key=canonical_json_bytes)
    payload = {
        "protocol_version": bundle.protocol_version,
        "engine_image_digest": bundle.engine_image_digest,
        "indexes": normalized_indexes,
    }
    return domain_separated_digest(STRATEGY_DOMAIN_V2, payload)


def validator_index_name(spec: IndexSpec) -> str:
    """Derive a deterministic validator-owned index name from a safe AST."""

    suffix = domain_separated_digest(
        "planrace/2:index-name", spec.model_dump(mode="json")
    ).removeprefix("sha256:")[:20]
    return f"planrace_{suffix}"


def compile_index_sql(spec: IndexSpec) -> str:
    """Compile the restricted AST to SQLite DDL entirely on the validator.

    Identifiers have already passed the ASCII identifier grammar and are still
    quoted defensively.  Partial-index values are emitted from tagged literals,
    never from miner-provided SQL text.
    """

    unique = "UNIQUE " if spec.unique else ""
    columns = [
        f'{_quote_identifier(item.column)} {item.direction.upper()}' for item in spec.key_columns
    ]
    columns.extend(_quote_identifier(item) for item in spec.include_columns)
    sql = (
        f"CREATE {unique}INDEX {_quote_identifier(validator_index_name(spec))} "
        f"ON {_quote_identifier(spec.table)} ({', '.join(columns)})"
    )
    if spec.predicate is not None:
        sql += " WHERE " + " AND ".join(_compile_predicate(item) for item in spec.predicate.atoms)
    return sql


def _quote_identifier(value: str) -> str:
    return f'"{value}"'


def _compile_predicate(atom: PredicateAtom) -> str:
    column = _quote_identifier(atom.column)
    if atom.operator == "is_null":
        return f"{column} IS NULL"
    if atom.operator == "is_not_null":
        return f"{column} IS NOT NULL"
    operators = {"eq": "=", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
    return f"{column} {operators[atom.operator]} {_compile_literal(atom.value)}"


def _compile_literal(value: PredicateLiteral) -> str:
    if isinstance(value, IntegerLiteral):
        return str(value.value)
    if isinstance(value, BooleanLiteral):
        return "1" if value.value else "0"
    if isinstance(value, TextLiteral):
        return "'" + value.value.replace("'", "''") + "'"
    raise ValueError("NULL must be compiled through an IS NULL operator")


class ParameterRange(StrictV2Model):
    name: SafeIdentifier
    value_type: Literal["integer", "text", "boolean"]
    minimum: int | str | bool
    maximum: int | str | bool
    distribution: Literal["uniform", "log_uniform", "categorical", "boundary_weighted"]

    @model_validator(mode="after")
    def validate_range_types(self) -> ParameterRange:
        expected = {"integer": int, "text": str, "boolean": bool}[self.value_type]
        if type(self.minimum) is not expected or type(self.maximum) is not expected:
            raise ValueError("parameter range endpoints do not match value_type")
        if self.value_type != "boolean" and self.minimum > self.maximum:  # type: ignore[operator]
            raise ValueError("parameter range minimum exceeds maximum")
        return self


class PublishedStatistics(StrictV2Model):
    row_count_min: Annotated[int, Field(ge=0)]
    row_count_max: Annotated[int, Field(ge=0)]
    selectivity_min_bps: Annotated[int, Field(ge=0, le=10_000)]
    selectivity_max_bps: Annotated[int, Field(ge=0, le=10_000)]
    data_profiles: Annotated[
        tuple[Literal["uniform", "skewed", "correlated", "null_heavy", "duplicate_heavy"], ...],
        Field(min_length=1),
    ]

    @model_validator(mode="after")
    def validate_bounds(self) -> PublishedStatistics:
        if self.row_count_min > self.row_count_max:
            raise ValueError("row count bounds are inverted")
        if self.selectivity_min_bps > self.selectivity_max_bps:
            raise ValueError("selectivity bounds are inverted")
        return self


class PublicTrainingFixture(StrictV2Model):
    fixture_id: SafeIdentifier
    generator_seed_hex: Hex32Bytes
    content_digest: Sha256Digest
    row_count: Annotated[int, Field(ge=0)]


class ArtifactBudget(StrictV2Model):
    max_indexes: Annotated[int, Field(ge=0, le=MAX_INDEXES_V2)] = MAX_INDEXES_V2
    max_columns_per_index: Annotated[int, Field(ge=1, le=MAX_COLUMNS_PER_INDEX_V2)] = (
        MAX_COLUMNS_PER_INDEX_V2
    )
    max_predicates_per_index: Annotated[int, Field(ge=0, le=MAX_PREDICATES_V2)] = (
        MAX_PREDICATES_V2
    )
    # The signed HTTP response and worker input envelopes are bounded at the
    # transport layer; a task cannot advertise an artifact larger than the
    # production path can receive and verify.
    max_bundle_bytes: Annotated[int, Field(ge=1024, le=65_536)] = 65_536


class ArtifactGrammar(StrictV2Model):
    artifact_type: Literal["structured-index-spec-v1"] = "structured-index-spec-v1"
    allowed_predicate_operators: tuple[
        Literal["eq", "ne", "lt", "lte", "gt", "gte", "is_null", "is_not_null"], ...
    ] = ("eq", "ne", "lt", "lte", "gt", "gte", "is_null", "is_not_null")
    allows_unique: bool = True
    allows_partial: bool = True
    allows_raw_sql: Literal[False] = False
    miner_controls_index_name: Literal[False] = False


class PublicTaskV2(StrictV2Model):
    """Public task contents; private seeds and holdout roots never appear here."""

    protocol_version: Literal["planrace/2"] = PROTOCOL_VERSION_V2
    task_id: OpaqueId
    validator_hotkey: Hotkey
    engine_image_digest: Sha256Digest
    generator_source_digest: Sha256Digest
    benchmark_policy_digest: Sha256Digest
    benchmark_family_id: BenchmarkFamilyId = "custom"
    schema_sql: SqlTextV2
    reference_sql: SqlTextV2
    public_training_fixture: PublicTrainingFixture
    parameter_ranges: Annotated[tuple[ParameterRange, ...], Field(min_length=1)]
    published_statistics: PublishedStatistics
    artifact_budget: ArtifactBudget = Field(default_factory=ArtifactBudget)
    artifact_grammar: ArtifactGrammar = Field(default_factory=ArtifactGrammar)
    hidden_holdout_count: Annotated[int, Field(ge=2, le=64)]
    commitment: Sha256Digest
    deadline_unix_ms: Annotated[int, Field(gt=0)]


class HiddenFixtureDescriptor(StrictV2Model):
    fixture_id: SafeIdentifier
    content_digest: Sha256Digest
    database_file_digest: Sha256Digest | None = None
    parameter_set_digest: Sha256Digest
    row_count: Annotated[int, Field(ge=0)]


class TaskRevealV2(StrictV2Model):
    protocol_version: Literal["planrace/2"] = PROTOCOL_VERSION_V2
    task_id: OpaqueId
    secret_seed_hex: Hex32Bytes
    salt_hex: Hex32Bytes
    hidden_fixtures: Annotated[
        tuple[HiddenFixtureDescriptor, ...], Field(min_length=2, max_length=64)
    ]
    hidden_fixture_merkle_root: Sha256Digest


class OptimizationRequestV2(StrictV2Model):
    protocol_version: Literal["planrace/2"] = PROTOCOL_VERSION_V2
    request_id: OpaqueId
    task: PublicTaskV2
    validator_hotkey: Hotkey
    miner_hotkey: Hotkey
    request_nonce: Annotated[int, Field(ge=0)]
    issued_at_unix_ms: Annotated[int, Field(gt=0)]
    expires_at_unix_ms: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def validate_request(self) -> OptimizationRequestV2:
        if self.validator_hotkey != self.task.validator_hotkey:
            raise ValueError("request validator does not own the task")
        if self.expires_at_unix_ms <= self.issued_at_unix_ms:
            raise ValueError("request expiry must follow issue time")
        return self


def optimization_request_digest(request: OptimizationRequestV2) -> str:
    return domain_separated_digest(REQUEST_DOMAIN_V2, request)


class SignedOptimizationResponse(StrictV2Model):
    protocol_version: Literal["planrace/2"] = PROTOCOL_VERSION_V2
    request_id: OpaqueId
    task_id: OpaqueId
    request_digest: Sha256Digest
    validator_hotkey: Hotkey
    miner_hotkey: Hotkey
    request_nonce: Annotated[int, Field(ge=0)]
    issued_at_unix_ms: Annotated[int, Field(gt=0)]
    expires_at_unix_ms: Annotated[int, Field(gt=0)]
    artifact_digest: Sha256Digest
    artifact: OptimizationBundle
    signature: SignatureHex

    @model_validator(mode="after")
    def validate_response_links(self) -> SignedOptimizationResponse:
        if self.task_id != self.artifact.task_id:
            raise ValueError("response task_id does not match artifact")
        if self.artifact_digest != self.artifact.artifact_digest:
            raise ValueError("response artifact_digest does not match artifact")
        if self.expires_at_unix_ms <= self.issued_at_unix_ms:
            raise ValueError("response expiry must follow issue time")
        return self


def optimization_response_signing_bytes(response: SignedOptimizationResponse) -> bytes:
    payload = response.model_dump(mode="json", exclude={"signature"})
    canonical = canonical_json_bytes(payload)
    domain = RESPONSE_DOMAIN_V2.encode("ascii")
    return len(domain).to_bytes(2, "big") + domain + len(canonical).to_bytes(8, "big") + canonical
