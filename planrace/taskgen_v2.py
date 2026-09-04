"""Opaque task creation and fail-closed commit/seal/reveal for PlanRace v2."""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol

from planrace.models_v2 import (
    COMMITMENT_DOMAIN_V2,
    PROTOCOL_VERSION_V2,
    ArtifactBudget,
    ArtifactGrammar,
    BenchmarkFamilyId,
    Hex32Bytes,
    HiddenFixtureDescriptor,
    Hotkey,
    OpaqueId,
    OptimizationBundle,
    OptimizationRequestV2,
    ParameterRange,
    PublicTaskV2,
    PublicTrainingFixture,
    PublishedStatistics,
    Sha256Digest,
    SignedOptimizationResponse,
    StrictV2Model,
    TaskRevealV2,
    domain_separated_digest,
)

if TYPE_CHECKING:
    from planrace.auth_v2 import ResponseReplayStore


class EntropySource(Protocol):
    """CSPRNG interface; alternate implementations are only for explicit tests."""

    def token_bytes(self, size: int) -> bytes: ...


class SystemEntropy:
    """The only production entropy implementation."""

    def token_bytes(self, size: int) -> bytes:
        return secrets.token_bytes(size)


class TaskCommitmentPayloadV2(StrictV2Model):
    """Every field cryptographically bound by a v2 task commitment."""

    protocol_version: Literal["planrace/2"]
    task_id: OpaqueId
    validator_hotkey: Hotkey
    engine_image_digest: Sha256Digest
    generator_source_digest: Sha256Digest
    benchmark_policy_digest: Sha256Digest
    benchmark_family_id: BenchmarkFamilyId
    schema_sql: str
    reference_sql: str
    public_training_fixture: PublicTrainingFixture
    parameter_ranges: tuple[ParameterRange, ...]
    published_statistics: PublishedStatistics
    artifact_budget: ArtifactBudget
    artifact_grammar: ArtifactGrammar
    secret_seed_hex: Hex32Bytes
    salt_hex: Hex32Bytes
    hidden_fixture_merkle_root: Sha256Digest
    deadline_unix_ms: int


HiddenFixtureFactory = Callable[[bytes], Sequence[HiddenFixtureDescriptor]]


@dataclass(frozen=True, slots=True)
class PrivateTaskV2:
    """Validator-only task state.  Never serialize this object to miners."""

    public: PublicTaskV2
    reveal: TaskRevealV2


def create_task_v2(
    *,
    validator_hotkey: str,
    engine_image_digest: str,
    generator_source_digest: str,
    benchmark_policy_digest: str,
    benchmark_family_id: str = "custom",
    schema_sql: str,
    reference_sql: str,
    public_training_fixture: PublicTrainingFixture,
    parameter_ranges: tuple[ParameterRange, ...],
    published_statistics: PublishedStatistics,
    deadline_unix_ms: int,
    hidden_fixture_factory: HiddenFixtureFactory,
    artifact_budget: ArtifactBudget | None = None,
    artifact_grammar: ArtifactGrammar | None = None,
    entropy: EntropySource | None = None,
) -> PrivateTaskV2:
    """Create a task using independent OS-CSPRNG values.

    ``entropy`` exists to make unit tests auditable.  Production callers must
    omit it, which selects :class:`SystemEntropy` and ``secrets.token_bytes``.
    The private fixture factory receives the new 256-bit secret seed; only its
    resulting fixture commitments are bound, and no secret reaches the public
    task.
    """

    random_source = entropy or SystemEntropy()
    task_id = _draw_exact(random_source, 16).hex()
    secret_seed = _draw_exact(random_source, 32)
    salt = _draw_exact(random_source, 32)
    if salt == secret_seed:
        # Independence is established by separate draws.  Also fail closed on
        # a catastrophically broken or test entropy source that repeats bytes.
        raise ValueError("entropy source repeated the task seed as the salt")
    hidden_fixtures = tuple(hidden_fixture_factory(secret_seed))
    if len(hidden_fixtures) < 2:
        raise ValueError("PlanRace v2 requires at least two private holdout fixtures")
    if len({item.fixture_id for item in hidden_fixtures}) != len(hidden_fixtures):
        raise ValueError("hidden fixture IDs must be unique")
    hidden_root = hidden_fixture_merkle_root(hidden_fixtures)
    reveal = TaskRevealV2(
        task_id=task_id,
        secret_seed_hex=secret_seed.hex(),
        salt_hex=salt.hex(),
        hidden_fixtures=hidden_fixtures,
        hidden_fixture_merkle_root=hidden_root,
    )
    payload = _commitment_payload(
        task_id=task_id,
        validator_hotkey=validator_hotkey,
        engine_image_digest=engine_image_digest,
        generator_source_digest=generator_source_digest,
        benchmark_policy_digest=benchmark_policy_digest,
        benchmark_family_id=benchmark_family_id,
        schema_sql=schema_sql,
        reference_sql=reference_sql,
        public_training_fixture=public_training_fixture,
        parameter_ranges=parameter_ranges,
        published_statistics=published_statistics,
        artifact_budget=artifact_budget or ArtifactBudget(),
        artifact_grammar=artifact_grammar or ArtifactGrammar(),
        deadline_unix_ms=deadline_unix_ms,
        reveal=reveal,
    )
    public = PublicTaskV2(
        task_id=task_id,
        validator_hotkey=validator_hotkey,
        engine_image_digest=engine_image_digest,
        generator_source_digest=generator_source_digest,
        benchmark_policy_digest=benchmark_policy_digest,
        benchmark_family_id=benchmark_family_id,
        schema_sql=schema_sql,
        reference_sql=reference_sql,
        public_training_fixture=public_training_fixture,
        parameter_ranges=parameter_ranges,
        published_statistics=published_statistics,
        artifact_budget=artifact_budget or ArtifactBudget(),
        artifact_grammar=artifact_grammar or ArtifactGrammar(),
        hidden_holdout_count=len(hidden_fixtures),
        commitment=domain_separated_digest(COMMITMENT_DOMAIN_V2, payload),
        deadline_unix_ms=deadline_unix_ms,
    )
    return PrivateTaskV2(public=public, reveal=reveal)


def hidden_fixture_merkle_root(fixtures: Sequence[HiddenFixtureDescriptor]) -> str:
    """Commit to an ordered fixture list with index-bound Merkle leaves."""

    if len(fixtures) < 2:
        raise ValueError("at least two hidden fixtures are required")
    level = [
        domain_separated_digest(
            "planrace/2:hidden-fixture-leaf",
            {"index": index, "fixture": fixture.model_dump(mode="json")},
        )
        for index, fixture in enumerate(fixtures)
    ]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            domain_separated_digest(
                "planrace/2:hidden-fixture-node", {"left": level[i], "right": level[i + 1]}
            )
            for i in range(0, len(level), 2)
        ]
    return level[0]


def audit_task_reveal(
    public: PublicTaskV2,
    reveal: TaskRevealV2,
    *,
    regenerate: HiddenFixtureFactory | None = None,
) -> bool:
    """Audit a post-deadline reveal and optionally regenerate every fixture."""

    if public.task_id != reveal.task_id:
        return False
    if public.hidden_holdout_count != len(reveal.hidden_fixtures):
        return False
    calculated_root = hidden_fixture_merkle_root(reveal.hidden_fixtures)
    if calculated_root != reveal.hidden_fixture_merkle_root:
        return False
    if regenerate is not None:
        regenerated = tuple(regenerate(bytes.fromhex(reveal.secret_seed_hex)))
        if regenerated != reveal.hidden_fixtures:
            return False
    payload = _commitment_payload(
        task_id=public.task_id,
        validator_hotkey=public.validator_hotkey,
        engine_image_digest=public.engine_image_digest,
        generator_source_digest=public.generator_source_digest,
        benchmark_policy_digest=public.benchmark_policy_digest,
        benchmark_family_id=public.benchmark_family_id,
        schema_sql=public.schema_sql,
        reference_sql=public.reference_sql,
        public_training_fixture=public.public_training_fixture,
        parameter_ranges=public.parameter_ranges,
        published_statistics=public.published_statistics,
        artifact_budget=public.artifact_budget,
        artifact_grammar=public.artifact_grammar,
        deadline_unix_ms=public.deadline_unix_ms,
        reveal=reveal,
    )
    return public.commitment == domain_separated_digest(COMMITMENT_DOMAIN_V2, payload)


def _commitment_payload(
    *,
    task_id: str,
    validator_hotkey: str,
    engine_image_digest: str,
    generator_source_digest: str,
    benchmark_policy_digest: str,
    benchmark_family_id: str,
    schema_sql: str,
    reference_sql: str,
    public_training_fixture: PublicTrainingFixture,
    parameter_ranges: tuple[ParameterRange, ...],
    published_statistics: PublishedStatistics,
    artifact_budget: ArtifactBudget,
    artifact_grammar: ArtifactGrammar,
    deadline_unix_ms: int,
    reveal: TaskRevealV2,
) -> TaskCommitmentPayloadV2:
    return TaskCommitmentPayloadV2(
        protocol_version=PROTOCOL_VERSION_V2,
        task_id=task_id,
        validator_hotkey=validator_hotkey,
        engine_image_digest=engine_image_digest,
        generator_source_digest=generator_source_digest,
        benchmark_policy_digest=benchmark_policy_digest,
        benchmark_family_id=benchmark_family_id,
        schema_sql=schema_sql,
        reference_sql=reference_sql,
        public_training_fixture=public_training_fixture,
        parameter_ranges=parameter_ranges,
        published_statistics=published_statistics,
        artifact_budget=artifact_budget,
        artifact_grammar=artifact_grammar,
        secret_seed_hex=reveal.secret_seed_hex,
        salt_hex=reveal.salt_hex,
        hidden_fixture_merkle_root=reveal.hidden_fixture_merkle_root,
        deadline_unix_ms=deadline_unix_ms,
    )


def _draw_exact(source: EntropySource, size: int) -> bytes:
    value = source.token_bytes(size)
    if not isinstance(value, bytes) or len(value) != size:
        raise ValueError(f"entropy source must return exactly {size} bytes")
    return value


class TaskPhase(StrEnum):
    OPEN = "open"
    SEALED = "sealed"
    REVEALED = "revealed"


class LifecycleError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TaskLifecycleV2:
    """Thread-safe deadline, submission seal, and reveal state machine."""

    def __init__(self, task: PrivateTaskV2) -> None:
        self._task = task
        self._phase = TaskPhase.OPEN
        self._submissions: dict[str, SignedOptimizationResponse] = {}
        self._lock = threading.Lock()

    @property
    def public_task(self) -> PublicTaskV2:
        return self._task.public

    @property
    def phase(self) -> TaskPhase:
        with self._lock:
            return self._phase

    def submit_verified(
        self,
        response: SignedOptimizationResponse,
        *,
        request: OptimizationRequestV2,
        expected_miner_uid: int,
        metagraph_hotkeys: Mapping[int, str],
        replay_store: ResponseReplayStore,
        now_unix_ms: int,
    ) -> None:
        """Verify and store one response through a single non-bypassable boundary.

        A lifecycle must never accept a caller's assertion that a response was
        verified.  Signature, receiver, request, nonce, task, metagraph and
        replay checks therefore happen inside the state transition that stores
        the response.
        """

        # Keep the benchmark worker's import graph free of Bittensor. The
        # lifecycle boundary is the only task-generation path that needs
        # signature verification.
        from planrace.auth_v2 import verify_signed_response

        with self._lock:
            if self._phase is not TaskPhase.OPEN:
                raise LifecycleError("submissions_sealed")
            if now_unix_ms >= self._task.public.deadline_unix_ms:
                raise LifecycleError("submission_after_deadline")
            if request.task != self._task.public:
                raise LifecycleError("request_not_for_lifecycle_task")
            if response.task_id != self._task.public.task_id:
                raise LifecycleError("wrong_task")
            if response.request_id in self._submissions:
                raise LifecycleError("duplicate_request")
            verify_signed_response(
                response,
                request=request,
                expected_miner_uid=expected_miner_uid,
                metagraph_hotkeys=metagraph_hotkeys,
                replay_store=replay_store,
                now_unix_ms=now_unix_ms,
            )
            self._submissions[response.request_id] = response

    def seal(self, *, now_unix_ms: int) -> tuple[SignedOptimizationResponse, ...]:
        with self._lock:
            if now_unix_ms < self._task.public.deadline_unix_ms:
                raise LifecycleError("seal_before_deadline")
            if self._phase is TaskPhase.REVEALED:
                raise LifecycleError("already_revealed")
            self._phase = TaskPhase.SEALED
            return tuple(self._submissions.values())

    def reveal(self, *, now_unix_ms: int) -> TaskRevealV2:
        with self._lock:
            if now_unix_ms < self._task.public.deadline_unix_ms:
                raise LifecycleError("reveal_before_deadline")
            if self._phase is TaskPhase.OPEN:
                raise LifecycleError("submissions_not_sealed")
            self._phase = TaskPhase.REVEALED
            return self._task.reveal

    def sealed_bundles(self) -> tuple[OptimizationBundle, ...]:
        with self._lock:
            if self._phase is TaskPhase.OPEN:
                raise LifecycleError("submissions_not_sealed")
            return tuple(item.artifact for item in self._submissions.values())
