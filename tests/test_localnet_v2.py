import asyncio
from dataclasses import asdict
from pathlib import Path

import bittensor as bt
import pytest

from planrace.benchmark_v2 import QUERY_FAMILIES
from planrace.evaluation_v2 import create_benchmark_task_v2
from planrace.localnet_v2 import PROFILE_NAMES, bundle_for_profile, strategy_for_profile
from planrace.models_v2 import optimization_strategy_digest
from planrace.scoring_v2 import EpochObservation
from scripts.run_localnet_v2 import (
    MINER_COUNT,
    _load_epoch_checkpoint,
    _load_run_input,
    _write_json,
    _write_run_input,
)


class FixedEntropy:
    def __init__(self) -> None:
        self.values = [b"l" * 16, b"s" * 32, b"z" * 32]

    def token_bytes(self, size: int) -> bytes:
        value = self.values.pop(0)
        assert len(value) == size
        return value


def _private_task(family: str):
    validator = bt.sp_core.Keypair.create_from_uri("//PlanRaceValidator0")
    return create_benchmark_task_v2(
        validator_hotkey=validator.ss58_address,
        engine_image_digest="sha256:" + "1" * 64,
        family_id=family,
        deadline_unix_ms=2_000_000,
        entropy=FixedEntropy(),
    )


def _task(family: str):
    return _private_task(family).public


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


def test_localnet_run_input_round_trips_for_resume(tmp_path: Path) -> None:
    task = _private_task(QUERY_FAMILIES[0].family_id)
    image = "sha256:" + "1" * 64
    dispatch = {
        "epoch": 0,
        "task_public": task.public.model_dump(mode="json"),
        "outcomes": [],
    }
    path = tmp_path / "run-input.json"

    _write_run_input(
        path,
        started_at="2026-01-01T00:00:00Z",
        epochs=1,
        worker_image=image,
        dispatches=[dispatch],
        tasks=[task],
    )
    started_at, dispatches, tasks = _load_run_input(
        path,
        epochs=1,
        worker_image=image,
    )

    assert started_at == "2026-01-01T00:00:00Z"
    assert dispatches == [dispatch]
    assert tasks == [task]
    assert not (tmp_path / "run-input.json.tmp").exists()


def test_localnet_epoch_checkpoint_round_trips(tmp_path: Path) -> None:
    task = _private_task(QUERY_FAMILIES[0].family_id)
    record = {"epoch": 0, "task_public": task.public.model_dump(mode="json")}
    observations = [
        EpochObservation(
            miner_id=f"miner-{index:02}",
            epoch=0,
            family=task.public.benchmark_family_id,
            task_id=task.public.task_id,
            task_commitment=task.public.commitment,
            evidence_digest=f"evidence-{index}",
            reward=1.0,
            available=True,
            correct=True,
            compliant=True,
            strategy_digest=f"strategy-{index}",
            behavior_digest=f"behavior-{index}",
        )
        for index in range(MINER_COUNT)
    ]
    payload = {
        **record,
        "task_reveal": task.reveal.model_dump(mode="json"),
        "reveal_verified": True,
        "observations": [asdict(item) for item in observations],
    }
    path = tmp_path / "checkpoints" / "epoch-000.json"
    _write_json(path, payload)

    loaded_payload, loaded_observations = _load_epoch_checkpoint(
        path,
        record=record,
        task=task,
    )

    assert loaded_payload == payload
    assert loaded_observations == observations
