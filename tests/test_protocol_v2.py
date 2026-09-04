import json
from typing import Any, cast

import bittensor as bt
import pytest
from pydantic import ValidationError

from planrace.models_v2 import (
    BooleanLiteral,
    BundleMetadata,
    HiddenFixtureDescriptor,
    IndexColumn,
    IndexSpec,
    IntegerLiteral,
    NullLiteral,
    OptimizationBundle,
    OptimizationRequestV2,
    ParameterRange,
    PredicateAtom,
    PredicateExpression,
    PublicTrainingFixture,
    PublishedStatistics,
    TextLiteral,
    canonical_json_bytes,
    compile_index_sql,
    domain_separated_digest,
    optimization_strategy_digest,
    validator_index_name,
)
from planrace.taskgen_v2 import (
    LifecycleError,
    PrivateTaskV2,
    SystemEntropy,
    TaskLifecycleV2,
    audit_task_reveal,
    create_task_v2,
    hidden_fixture_merkle_root,
)

ALICE = bt.sp_core.Keypair.create_from_uri("//Alice")


class FixedEntropy:
    def __init__(self, task_byte: int = 10, seed_byte: int = 11, salt_byte: int = 12) -> None:
        self.values = [bytes([task_byte]) * 16, bytes([seed_byte]) * 32, bytes([salt_byte]) * 32]
        self.requested_sizes: list[int] = []

    def token_bytes(self, size: int) -> bytes:
        self.requested_sizes.append(size)
        value = self.values.pop(0)
        return value


def fixture_factory(seed: bytes) -> tuple[HiddenFixtureDescriptor, ...]:
    seed_marker = seed.hex()[:8]
    return tuple(
        HiddenFixtureDescriptor(
            fixture_id=f"holdout_{index}_{seed_marker}",
            content_digest=domain_separated_digest(
                "planrace/2:test-fixture", {"index": index, "seed": seed.hex()}
            ),
            parameter_set_digest=domain_separated_digest(
                "planrace/2:test-parameters", {"index": index, "seed": seed.hex()}
            ),
            row_count=100 + index,
        )
        for index in range(3)
    )


def private_task(*, entropy: FixedEntropy | None = None) -> PrivateTaskV2:
    return create_task_v2(
        validator_hotkey=ALICE.ss58_address,
        engine_image_digest="sha256:" + "1" * 64,
        generator_source_digest="sha256:" + "2" * 64,
        benchmark_policy_digest="sha256:" + "3" * 64,
        schema_sql="CREATE TABLE orders(id INTEGER PRIMARY KEY, cents INTEGER NOT NULL)",
        reference_sql="SELECT SUM(cents) FROM orders WHERE cents >= ?",
        public_training_fixture=PublicTrainingFixture(
            fixture_id="training",
            generator_seed_hex="4" * 64,
            content_digest="sha256:" + "5" * 64,
            row_count=100,
        ),
        parameter_ranges=(
            ParameterRange(
                name="minimum_cents",
                value_type="integer",
                minimum=0,
                maximum=100_000,
                distribution="boundary_weighted",
            ),
        ),
        published_statistics=PublishedStatistics(
            row_count_min=0,
            row_count_max=1_000_000,
            selectivity_min_bps=0,
            selectivity_max_bps=10_000,
            data_profiles=("uniform", "skewed", "correlated", "null_heavy"),
        ),
        deadline_unix_ms=2_000_000,
        hidden_fixture_factory=fixture_factory,
        entropy=entropy or FixedEntropy(),
    )


def bundle(task_id: str) -> OptimizationBundle:
    spec = IndexSpec(
        table="orders",
        key_columns=(
            IndexColumn(column="customer_id"),
            IndexColumn(column="cents", direction="desc"),
        ),
        include_columns=("status",),
        predicate=PredicateExpression(
            atoms=(
                PredicateAtom(column="status", operator="eq", value=TextLiteral(value="paid")),
                PredicateAtom(column="cents", operator="gte", value=IntegerLiteral(value=100)),
            )
        ),
    )
    return OptimizationBundle.create(
        task_id=task_id,
        engine_image_digest="sha256:" + "1" * 64,
        indexes=(spec,),
        metadata=BundleMetadata(
            strategy="cover paid orders",
            estimated_intent="mixed",
            rationale="Filter and ordering columns first.",
        ),
    )


def test_task_uses_independent_csprng_draws_and_opaque_id() -> None:
    entropy = FixedEntropy()
    task = private_task(entropy=entropy)
    assert entropy.requested_sizes == [16, 32, 32]
    assert task.public.protocol_version == "planrace/2"
    assert len(task.public.task_id) == 32
    assert task.public.task_id == bytes([10] * 16).hex()
    assert task.reveal.secret_seed_hex != task.reveal.salt_hex
    assert audit_task_reveal(task.public, task.reveal, regenerate=fixture_factory)


def test_system_entropy_returns_requested_csprng_bytes() -> None:
    assert len(SystemEntropy().token_bytes(32)) == 32


def test_task_creation_fails_closed_on_broken_entropy_and_holdouts() -> None:
    repeated = FixedEntropy(seed_byte=11, salt_byte=11)
    with pytest.raises(ValueError, match="repeated"):
        private_task(entropy=repeated)

    wrong_size = FixedEntropy()
    wrong_size.values[0] = b"short"
    with pytest.raises(ValueError, match="exactly 16"):
        private_task(entropy=wrong_size)

    with pytest.raises(ValueError, match="at least two"):
        create_task_v2(
            **_task_creation_kwargs(),
            hidden_fixture_factory=lambda _seed: fixture_factory(b"x" * 32)[:1],
            entropy=FixedEntropy(),
        )

    duplicate = fixture_factory(b"x" * 32)
    duplicate = (
        duplicate[0],
        duplicate[1].model_copy(update={"fixture_id": duplicate[0].fixture_id}),
    )
    with pytest.raises(ValueError, match="unique"):
        create_task_v2(
            **_task_creation_kwargs(),
            hidden_fixture_factory=lambda _seed: duplicate,
            entropy=FixedEntropy(),
        )


def test_public_task_does_not_reveal_private_seed_salt_or_fixture_root() -> None:
    task = private_task()
    public_json = task.public.model_dump_json()
    assert task.reveal.secret_seed_hex not in public_json
    assert task.reveal.salt_hex not in public_json
    assert task.reveal.hidden_fixture_merkle_root not in public_json
    for fixture in task.reveal.hidden_fixtures:
        assert fixture.content_digest not in public_json


@pytest.mark.parametrize(
    ("target", "replacement"),
    [
        ("task_id", "ff" * 16),
        ("validator_hotkey", bt.sp_core.Keypair.create_from_uri("//Bob").ss58_address),
        ("engine_image_digest", "sha256:" + "a" * 64),
        ("generator_source_digest", "sha256:" + "b" * 64),
        ("benchmark_policy_digest", "sha256:" + "c" * 64),
        ("deadline_unix_ms", 2_000_001),
    ],
)
def test_commitment_rejects_tampered_public_binding(target: str, replacement: object) -> None:
    task = private_task()
    tampered = task.public.model_copy(update={target: replacement})
    assert not audit_task_reveal(tampered, task.reveal)


def test_commitment_rejects_tampered_seed_salt_and_holdout() -> None:
    task = private_task()
    assert not audit_task_reveal(
        task.public, task.reveal.model_copy(update={"secret_seed_hex": "d" * 64})
    )
    assert not audit_task_reveal(task.public, task.reveal.model_copy(update={"salt_hex": "e" * 64}))
    fixtures = list(task.reveal.hidden_fixtures)
    fixtures[0] = fixtures[0].model_copy(update={"row_count": 999})
    assert not audit_task_reveal(
        task.public, task.reveal.model_copy(update={"hidden_fixtures": tuple(fixtures)})
    )


def test_commitment_binds_complete_public_workload_and_artifact_policy() -> None:
    task = private_task()
    public = task.public
    mutations = (
        {"schema_sql": "CREATE TABLE changed(id INTEGER PRIMARY KEY)"},
        {"reference_sql": "SELECT 1"},
        {"benchmark_family_id": "changed-family"},
        {
            "public_training_fixture": public.public_training_fixture.model_copy(
                update={"row_count": public.public_training_fixture.row_count + 1}
            )
        },
        {"parameter_ranges": (public.parameter_ranges[0].model_copy(update={"maximum": 99_999}),)},
        {
            "published_statistics": public.published_statistics.model_copy(
                update={"row_count_max": public.published_statistics.row_count_max + 1}
            )
        },
        {"artifact_budget": public.artifact_budget.model_copy(update={"max_indexes": 0})},
        {"artifact_grammar": public.artifact_grammar.model_copy(update={"allows_unique": False})},
    )
    for mutation in mutations:
        assert not audit_task_reveal(public.model_copy(update=mutation), task.reveal)


def test_reveal_audit_rejects_wrong_identity_count_root_and_regeneration() -> None:
    task = private_task()
    assert not audit_task_reveal(task.public, task.reveal.model_copy(update={"task_id": "f0" * 16}))
    assert not audit_task_reveal(
        task.public.model_copy(update={"hidden_holdout_count": 2}), task.reveal
    )
    assert not audit_task_reveal(
        task.public,
        task.reveal.model_copy(update={"hidden_fixture_merkle_root": "sha256:" + "0" * 64}),
    )
    assert not audit_task_reveal(
        task.public,
        task.reveal,
        regenerate=lambda seed: tuple(reversed(fixture_factory(seed))),
    )
    with pytest.raises(ValueError, match="at least two"):
        hidden_fixture_merkle_root(task.reveal.hidden_fixtures[:1])


def test_canonical_json_is_order_independent_and_forbids_floats() -> None:
    left = {"z": [3, 2, 1], "a": {"two": 2, "one": 1}}
    right = {"a": {"one": 1, "two": 2}, "z": [3, 2, 1]}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert domain_separated_digest("planrace/2:test", left) == domain_separated_digest(
        "planrace/2:test", right
    )
    with pytest.raises(TypeError, match="floats"):
        canonical_json_bytes({"unstable": 0.1})
    with pytest.raises(ValueError, match="domain"):
        domain_separated_digest("other/2:test", {"safe": True})
    with pytest.raises(TypeError, match="keys"):
        canonical_json_bytes({1: "not a string"})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="unsupported"):
        canonical_json_bytes({"bytes": b"not-json"})


def test_canonical_digest_property_changes_for_mutations() -> None:
    for index in range(100):
        payload = {"nonce": index * 7_919, "value": index**3 + 17}
        mutated = {**payload, "value": payload["value"] + 1}
        assert domain_separated_digest("planrace/2:property", payload) != domain_separated_digest(
            "planrace/2:property", mutated
        )


def test_structured_index_compiles_only_validator_derived_sql() -> None:
    artifact = bundle("ab" * 16)
    spec = artifact.indexes[0]
    sql = compile_index_sql(spec)
    assert validator_index_name(spec).startswith("planrace_")
    assert sql == (
        f'CREATE INDEX "{validator_index_name(spec)}" ON "orders" '
        '("customer_id" ASC, "cents" DESC, "status") '
        'WHERE "status" = \'paid\' AND "cents" >= 100'
    )
    assert "candidate_sql" not in artifact.model_dump()
    assert "index_name" not in json.dumps(artifact.model_dump(mode="json"))


def test_strategy_digest_ignores_cosmetic_metadata_but_binds_executable_ast() -> None:
    original = bundle("ab" * 16)
    original_spec = original.indexes[0]
    assert original_spec.predicate is not None
    second_spec = IndexSpec(
        table="orders",
        key_columns=(IndexColumn(column="status"),),
    )
    reordered_predicate = original_spec.model_copy(
        update={
            "predicate": original_spec.predicate.model_copy(
                update={"atoms": tuple(reversed(original_spec.predicate.atoms))}
            )
        }
    )
    with_two_indexes = OptimizationBundle.create(
        task_id=original.task_id,
        engine_image_digest=original.engine_image_digest,
        indexes=(original_spec, second_spec),
        metadata=original.metadata,
    )
    permuted = OptimizationBundle.create(
        task_id="ce" * 16,
        engine_image_digest=original.engine_image_digest,
        indexes=(second_spec, reordered_predicate),
        metadata=original.metadata,
    )
    cosmetic = OptimizationBundle.create(
        task_id="cd" * 16,
        engine_image_digest=original.engine_image_digest,
        indexes=original.indexes,
        metadata=BundleMetadata(
            strategy="renamed cosmetic strategy",
            estimated_intent="filter",
            rationale="Different prose must not evade duplicate grouping.",
        ),
    )
    changed = OptimizationBundle.create(
        task_id=original.task_id,
        engine_image_digest=original.engine_image_digest,
        indexes=(),
        metadata=original.metadata,
    )
    assert original.artifact_digest != cosmetic.artifact_digest
    assert optimization_strategy_digest(original) == optimization_strategy_digest(cosmetic)
    assert optimization_strategy_digest(original) != optimization_strategy_digest(changed)
    assert optimization_strategy_digest(with_two_indexes) == optimization_strategy_digest(permuted)


def test_unique_and_null_predicates_compile_without_raw_expressions() -> None:
    no_predicate = IndexSpec(table="users", key_columns=(IndexColumn(column="email"),), unique=True)
    assert compile_index_sql(no_predicate).startswith("CREATE UNIQUE INDEX")
    nulls = IndexSpec(
        table="users",
        key_columns=(IndexColumn(column="deleted_at"),),
        predicate=PredicateExpression(
            atoms=(
                PredicateAtom(column="deleted_at", operator="is_null", value=NullLiteral()),
                PredicateAtom(column="email", operator="is_not_null", value=NullLiteral()),
            )
        ),
    )
    assert compile_index_sql(nulls).endswith('WHERE "deleted_at" IS NULL AND "email" IS NOT NULL')


def test_predicate_text_is_literal_escaped_not_executable_sql() -> None:
    spec = IndexSpec(
        table="orders",
        key_columns=(IndexColumn(column="status"),),
        predicate=PredicateExpression(
            atoms=(
                PredicateAtom(
                    column="status",
                    operator="eq",
                    value=TextLiteral(value="x'; DROP TABLE orders;--"),
                ),
            )
        ),
    )
    sql = compile_index_sql(spec)
    assert "'x''; DROP TABLE orders;--'" in sql
    assert sql.count(";") == 2  # Both semicolons remain inside one quoted literal.


def test_index_rejects_expression_names_duplicate_columns_and_raw_sql() -> None:
    with pytest.raises(ValidationError):
        IndexColumn(column="lower(email)")
    with pytest.raises(ValidationError, match="repeat"):
        IndexSpec(
            table="orders",
            key_columns=(IndexColumn(column="status"),),
            include_columns=("status",),
        )
    with pytest.raises(ValidationError, match="unique indexes cannot contain"):
        IndexSpec(
            table="orders",
            key_columns=(IndexColumn(column="customer_id"),),
            include_columns=("status",),
            unique=True,
        )
    with pytest.raises(ValidationError):
        IndexSpec.model_validate(
            {
                "table": "orders",
                "key_columns": [{"column": "status"}],
                "raw_sql": "DROP TABLE orders",
            }
        )


def test_predicate_enforces_null_semantics_and_boolean_literals() -> None:
    with pytest.raises(ValidationError, match="NULL literals"):
        PredicateAtom(column="x", operator="eq")
    atom = PredicateAtom(column="active", operator="eq", value=BooleanLiteral(value=True))
    spec = IndexSpec(
        table="orders",
        key_columns=(IndexColumn(column="active"),),
        predicate=PredicateExpression(atoms=(atom,)),
    )
    assert compile_index_sql(spec).endswith('WHERE "active" = 1')


def test_bundle_digest_rejects_any_tampering() -> None:
    artifact = bundle("cd" * 16)
    raw = artifact.model_dump(mode="python")
    raw["metadata"]["rationale"] = "tampered"
    with pytest.raises(ValidationError, match="artifact_digest"):
        OptimizationBundle.model_validate(raw)


def test_public_range_statistics_and_request_validators_fail_closed() -> None:
    with pytest.raises(ValidationError, match="endpoints"):
        ParameterRange(
            name="bad",
            value_type="integer",
            minimum="1",
            maximum="2",
            distribution="uniform",
        )
    with pytest.raises(ValidationError, match="minimum"):
        ParameterRange(
            name="bad",
            value_type="integer",
            minimum=2,
            maximum=1,
            distribution="uniform",
        )
    with pytest.raises(ValidationError, match="row count"):
        PublishedStatistics(
            row_count_min=2,
            row_count_max=1,
            selectivity_min_bps=0,
            selectivity_max_bps=1,
            data_profiles=("uniform",),
        )
    with pytest.raises(ValidationError, match="selectivity"):
        PublishedStatistics(
            row_count_min=1,
            row_count_max=2,
            selectivity_min_bps=2,
            selectivity_max_bps=1,
            data_profiles=("uniform",),
        )
    public = private_task().public
    bob = bt.sp_core.Keypair.create_from_uri("//Bob")
    with pytest.raises(ValidationError, match="does not own"):
        OptimizationRequestV2(
            request_id="aa" * 16,
            task=public,
            validator_hotkey=bob.ss58_address,
            miner_hotkey=bob.ss58_address,
            request_nonce=1,
            issued_at_unix_ms=1,
            expires_at_unix_ms=2,
        )
    with pytest.raises(ValidationError, match="expiry"):
        OptimizationRequestV2(
            request_id="aa" * 16,
            task=public,
            validator_hotkey=public.validator_hotkey,
            miner_hotkey=bob.ss58_address,
            request_nonce=1,
            issued_at_unix_ms=2,
            expires_at_unix_ms=2,
        )


def test_lifecycle_rejects_early_reveal_and_late_submission() -> None:
    lifecycle = TaskLifecycleV2(private_task())
    with pytest.raises(LifecycleError, match="reveal_before_deadline"):
        lifecycle.reveal(now_unix_ms=1_999_999)
    with pytest.raises(LifecycleError, match="seal_before_deadline"):
        lifecycle.seal(now_unix_ms=1_999_999)
    lifecycle.seal(now_unix_ms=2_000_000)
    reveal = lifecycle.reveal(now_unix_ms=2_000_000)
    assert audit_task_reveal(lifecycle.public_task, reveal)
    with pytest.raises(LifecycleError, match="submissions_sealed"):
        # Type is irrelevant: phase rejection occurs before response access.
        lifecycle.submit_verified(
            cast(Any, None),
            request=cast(Any, None),
            expected_miner_uid=0,
            metagraph_hotkeys={},
            replay_store=cast(Any, None),
            now_unix_ms=2_000_001,
        )


def test_open_lifecycle_rejects_post_deadline_submission_before_body_access() -> None:
    lifecycle = TaskLifecycleV2(private_task())
    with pytest.raises(LifecycleError, match="submission_after_deadline"):
        lifecycle.submit_verified(
            cast(Any, None),
            request=cast(Any, None),
            expected_miner_uid=0,
            metagraph_hotkeys={},
            replay_store=cast(Any, None),
            now_unix_ms=2_000_000,
        )


def test_reveal_requires_explicit_submission_seal() -> None:
    lifecycle = TaskLifecycleV2(private_task())
    with pytest.raises(LifecycleError, match="submissions_not_sealed"):
        lifecycle.reveal(now_unix_ms=2_000_001)


def _task_creation_kwargs() -> dict[str, object]:
    return {
        "validator_hotkey": ALICE.ss58_address,
        "engine_image_digest": "sha256:" + "1" * 64,
        "generator_source_digest": "sha256:" + "2" * 64,
        "benchmark_policy_digest": "sha256:" + "3" * 64,
        "schema_sql": "CREATE TABLE orders(id INTEGER PRIMARY KEY, cents INTEGER NOT NULL)",
        "reference_sql": "SELECT SUM(cents) FROM orders WHERE cents >= ?",
        "public_training_fixture": PublicTrainingFixture(
            fixture_id="training",
            generator_seed_hex="4" * 64,
            content_digest="sha256:" + "5" * 64,
            row_count=100,
        ),
        "parameter_ranges": (
            ParameterRange(
                name="minimum_cents",
                value_type="integer",
                minimum=0,
                maximum=100_000,
                distribution="boundary_weighted",
            ),
        ),
        "published_statistics": PublishedStatistics(
            row_count_min=0,
            row_count_max=1_000_000,
            selectivity_min_bps=0,
            selectivity_max_bps=10_000,
            data_profiles=("uniform", "skewed"),
        ),
        "deadline_unix_ms": 2_000_000,
    }
