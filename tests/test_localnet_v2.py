import asyncio

import bittensor as bt
import pytest

from planrace.benchmark_v2 import QUERY_FAMILIES
from planrace.evaluation_v2 import create_benchmark_task_v2
from planrace.localnet_v2 import PROFILE_NAMES, bundle_for_profile, strategy_for_profile
from planrace.models_v2 import optimization_strategy_digest


class FixedEntropy:
    def __init__(self) -> None:
        self.values = [b"l" * 16, b"s" * 32, b"z" * 32]

    def token_bytes(self, size: int) -> bytes:
        value = self.values.pop(0)
        assert len(value) == size
        return value


def _task(family: str):
    validator = bt.sp_core.Keypair.create_from_uri("//PlanRaceValidator0")
    return create_benchmark_task_v2(
        validator_hotkey=validator.ss58_address,
        engine_image_digest="sha256:" + "1" * 64,
        family_id=family,
        deadline_unix_ms=2_000_000,
        entropy=FixedEntropy(),
    ).public


def test_all_public_profiles_are_behaviorally_exercisable() -> None:
    task = _task(QUERY_FAMILIES[0].family_id)
    bundles = {
        profile: bundle_for_profile(task, profile)
        for profile in PROFILE_NAMES
        if profile != "timeout-resource-attempt"
    }
    assert len(bundles) == 9
    assert bundles["baseline"].indexes == ()
    assert len(bundles["over-indexing"].indexes) == 4
    assert optimization_strategy_digest(bundles["copycat-sybil"]) == (
        optimization_strategy_digest(bundles["selective-index"])
    )
    assert optimization_strategy_digest(bundles["constant-answer-attempt"]) == (
        optimization_strategy_digest(bundles["baseline"])
    )
    robust_profiles = (
        "selective-index",
        "composite-index",
        "covering-index",
        "partial-index",
        "hybrid",
    )
    assert len(
        {optimization_strategy_digest(bundles[profile]) for profile in robust_profiles}
    ) == len(robust_profiles)


@pytest.mark.parametrize("family", [item.family_id for item in QUERY_FAMILIES])
def test_profiles_compile_for_every_family(family: str) -> None:
    task = _task(family)
    for profile in PROFILE_NAMES:
        if profile != "timeout-resource-attempt":
            bundle = bundle_for_profile(task, profile)
            assert bundle.task_id == task.task_id
            assert len(bundle.indexes) <= task.artifact_budget.max_indexes


def test_timeout_profile_is_really_async() -> None:
    task = _task(QUERY_FAMILIES[0].family_id)

    async def run() -> None:
        strategy = strategy_for_profile("timeout-resource-attempt", timeout_seconds=0.001)
        result = strategy(task)
        assert asyncio.iscoroutine(result)
        bundle = await result
        assert bundle.metadata.strategy == "timeout-resource-attempt"

    asyncio.run(run())
