#!/usr/bin/env python3
"""Generate the signed 30-epoch PlanRace v2 localnet evidence bundle."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import bittensor as bt
import httpx
from bittensor import calls
from bittensor.intents.weights import normalize

from planrace.auth_v2 import MemoryResponseReplayStore
from planrace.benchmark_v2 import (
    QUERY_FAMILIES,
    generate_hidden_fixtures,
    materialize_fixture,
)
from planrace.evaluation_v2 import (
    DEFAULT_MAX_UNIQUE_STRATEGIES_PER_TASK,
    create_benchmark_task_v2,
    evaluate_bundle_from_sandbox_results,
    holdout_evidence_digest,
)
from planrace.evidence import sign_manifest
from planrace.localnet_v2 import PROFILE_NAMES
from planrace.models_v2 import (
    ArtifactBudget,
    OptimizationRequestV2,
    PublicTaskV2,
    TaskRevealV2,
    domain_separated_digest,
    optimization_request_digest,
    optimization_strategy_digest,
)
from planrace.sandbox_v2 import (
    DEFAULT_SANDBOX_POLICY,
    SandboxRequestV2,
    WorkerFailure,
    run_docker_batch_worker,
)
from planrace.scoring_v2 import (
    AggregationPolicy,
    EpochObservation,
    ScheduledTask,
    aggregate_network,
    allocate_weights,
    kendall_tau_b,
)
from planrace.taskgen_v2 import PrivateTaskV2, audit_task_reveal
from planrace.validator_client_v2 import request_optimization_v2

DEFAULT_PORT = 8190
VALIDATOR_COUNT = 3
MINER_COUNT = 10


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _git_commit() -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable is required")
    return subprocess.check_output(  # noqa: S603 - fixed validator-owned argv
        [git, "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()


def _public_identities() -> tuple[list[bt.Keypair], list[bt.Keypair]]:
    validators = [
        bt.sp_core.Keypair.create_from_uri(f"//PlanRaceValidator{index}")
        for index in range(VALIDATOR_COUNT)
    ]
    miners = [
        bt.sp_core.Keypair.create_from_uri(f"//PlanRaceMinerV2-{index}")
        for index in range(MINER_COUNT)
    ]
    return validators, miners


def _auth_capture_hook(
    target: dict[str, str],
) -> Callable[[httpx.Request], Awaitable[None]]:
    async def capture(http_request: httpx.Request) -> None:
        for name, value in http_request.headers.items():
            if name.lower().startswith("x-bittensor-"):
                target[name.lower()] = value

    return capture


async def _wait_for_miners(base_port: int, processes: list[subprocess.Popen[bytes]]) -> None:
    deadline = time.monotonic() + 120.0
    async with httpx.AsyncClient(trust_env=False) as client:
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("a local miner exited before becoming healthy")
            ready = 0
            for index in range(MINER_COUNT):
                try:
                    response = await client.get(
                        f"http://127.0.0.1:{base_port + index}/health", timeout=0.5
                    )
                    ready += int(response.status_code == 200)
                except httpx.HTTPError:
                    pass
            if ready == MINER_COUNT:
                return
            await asyncio.sleep(0.2)
    raise RuntimeError("local miner readiness deadline elapsed")


def _start_miners(base_port: int, evidence_dir: Path) -> list[subprocess.Popen[bytes]]:
    log_dir = evidence_dir / "miner-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[bytes]] = []
    for index, profile in enumerate(PROFILE_NAMES):
        log = (log_dir / f"miner-{index:02}-{profile}.log").open("wb")
        process = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "scripts/run_local_miner_v2.py",
                "--profile",
                profile,
                "--index",
                str(index),
                "--port",
                str(base_port + index),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log.close()
        processes.append(process)
    return processes


def _stop_miners(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


async def _dispatch_epochs(
    *,
    epochs: int,
    base_port: int,
    image_digest: str,
    validators: list[bt.Keypair],
    miners: list[bt.Keypair],
) -> tuple[list[dict[str, Any]], list[Any]]:
    replay = MemoryResponseReplayStore()
    dispatch_records: list[dict[str, Any]] = []
    private_tasks: list[Any] = []
    metagraph = {index + 3: miner.ss58_address for index, miner in enumerate(miners)}
    latest_deadline = 0
    captured: dict[str, str] = {}
    async with httpx.AsyncClient(
        trust_env=False, event_hooks={"request": [_auth_capture_hook(captured)]}
    ) as client:
        for epoch in range(epochs):
            validator_index = epoch % VALIDATOR_COUNT
            round_index = epoch // VALIDATOR_COUNT
            family = QUERY_FAMILIES[round_index % len(QUERY_FAMILIES)].family_id
            validator = validators[validator_index]
            now = time.time_ns() // 1_000_000
            deadline = now + 120_000
            latest_deadline = max(latest_deadline, deadline)
            task = create_benchmark_task_v2(
                validator_hotkey=validator.ss58_address,
                engine_image_digest=image_digest,
                family_id=family,
                deadline_unix_ms=deadline,
                artifact_budget=ArtifactBudget(max_indexes=3),
            )
            private_tasks.append(task)
            epoch_outcomes: list[dict[str, Any]] = []
            for miner_index, miner in enumerate(miners):
                issued = time.time_ns() // 1_000_000
                request = OptimizationRequestV2(
                    request_id=secrets.token_hex(16),
                    task=task.public,
                    validator_hotkey=validator.ss58_address,
                    miner_hotkey=miner.ss58_address,
                    request_nonce=epoch * 100 + miner_index,
                    issued_at_unix_ms=issued,
                    expires_at_unix_ms=min(deadline, issued + 10_000),
                )
                captured.clear()
                outcome = await request_optimization_v2(
                    client,
                    wallet=validator,
                    endpoint=f"http://127.0.0.1:{base_port + miner_index}/v2/optimize",
                    receiver_ss58=miner.ss58_address,
                    request_model=request,
                    expected_miner_uid=miner_index + 3,
                    metagraph_hotkeys=metagraph,
                    replay_store=replay,
                    total_timeout_seconds=10.0,
                    allow_local_endpoint_for_tests=True,
                )
                epoch_outcomes.append(
                    {
                        "miner_id": f"miner-{miner_index:02}",
                        "uid": miner_index + 3,
                        "profile": PROFILE_NAMES[miner_index],
                        "request": request.model_dump(mode="json"),
                        "request_digest": optimization_request_digest(request),
                        "validator_auth_headers": dict(captured),
                        "accepted": outcome.accepted,
                        "failure_code": outcome.failure_code,
                        "status_code": outcome.status_code,
                        "response": (
                            outcome.response.model_dump(mode="json")
                            if outcome.response is not None
                            else None
                        ),
                    }
                )
            dispatch_records.append(
                {
                    "epoch": epoch,
                    "validator_index": validator_index,
                    "validator_hotkey": validator.ss58_address,
                    "family": family,
                    "task_public": task.public.model_dump(mode="json"),
                    "outcomes": epoch_outcomes,
                }
            )
            accepted = sum(bool(item["accepted"]) for item in epoch_outcomes)
            print(
                f"dispatch epoch={epoch:02} validator={validator_index} "
                f"family={family} accepted={accepted}/10",
                flush=True,
            )
            if accepted != MINER_COUNT - 1:
                raise RuntimeError(
                    f"epoch {epoch} expected exactly nine accepted responses, got {accepted}"
                )

    wait_seconds = max(0.0, (latest_deadline - time.time_ns() // 1_000_000) / 1000)
    if wait_seconds:
        await asyncio.sleep(wait_seconds + 0.05)
    return dispatch_records, private_tasks


def _evaluate_epoch(
    record: dict[str, Any],
    task: Any,
    *,
    image_digest: str,
) -> tuple[dict[str, Any], list[EpochObservation]]:
    submissions: dict[str, Any] = {}
    for outcome in record["outcomes"]:
        if outcome["accepted"] and outcome["response"] is not None:
            from planrace.models_v2 import SignedOptimizationResponse

            response = SignedOptimizationResponse.model_validate_json(
                json.dumps(outcome["response"], separators=(",", ":"))
            )
            submissions[outcome["miner_id"]] = response.artifact

    by_strategy: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for miner_id, bundle in submissions.items():
        by_strategy[optimization_strategy_digest(bundle)].append((miner_id, bundle))
    if len(by_strategy) > DEFAULT_MAX_UNIQUE_STRATEGIES_PER_TASK:
        raise RuntimeError("unique strategy budget exceeded before worker dispatch")

    strategy_evaluations: dict[str, Any] = {}
    observations: list[EpochObservation] = []
    with tempfile.TemporaryDirectory(prefix="planrace-localnet-v2-") as temporary:
        root = Path(temporary)
        fixtures = generate_hidden_fixtures(
            bytes.fromhex(task.reveal.secret_seed_hex),
            family_id=task.public.benchmark_family_id,
        )
        reveal_verified = audit_task_reveal(
            task.public,
            task.reveal,
            regenerate=lambda _seed: tuple(fixture.descriptor for fixture in fixtures),
        )
        if not reveal_verified:
            raise RuntimeError(f"epoch {record['epoch']} commitment/reveal audit failed")
        for index, fixture in enumerate(fixtures):
            materialize_fixture(fixture, root / f"fixture-{index:03}.sqlite3")
        batch_items: list[tuple[str, SandboxRequestV2]] = []
        ordered_strategies: list[tuple[str, Any]] = []
        for digest, members in sorted(by_strategy.items()):
            bundle = members[0][1]
            ordered_strategies.append((digest, bundle))
            for index, fixture in enumerate(fixtures):
                batch_items.append(
                    (
                        f"fixture-{index:03}.sqlite3",
                        SandboxRequestV2(
                            task=task.public,
                            reveal=task.reveal,
                            fixture=fixture.descriptor,
                            bundle=bundle,
                            parameters=fixture.parameters,
                            ordered=True,
                        ),
                    )
                )
        try:
            batch_results = run_docker_batch_worker(
                root,
                batch_items,
                image=image_digest,
                policy=DEFAULT_SANDBOX_POLICY,
            )
        except WorkerFailure as error:
            batch_results = ()
            record["batch_failure"] = error.code

    width = len(fixtures)
    if batch_results:
        for strategy_index, (digest, bundle) in enumerate(ordered_strategies):
            results = batch_results[strategy_index * width : (strategy_index + 1) * width]
            evaluation = evaluate_bundle_from_sandbox_results(task, bundle, results)
            evidence_digest = holdout_evidence_digest(evaluation)
            strategy_evaluations[digest] = {
                "evaluation": _evaluation_json(evaluation),
                "evidence_digest": evidence_digest,
                "miners": sorted(miner_id for miner_id, _ in by_strategy[digest]),
            }
            for miner_id, _ in by_strategy[digest]:
                observations.append(
                    EpochObservation(
                        miner_id=miner_id,
                        epoch=record["epoch"],
                        family=record["family"],
                        task_id=task.public.task_id,
                        task_commitment=task.public.commitment,
                        evidence_digest=evidence_digest,
                        reward=evaluation.reward,
                        available=True,
                        correct=evaluation.exact_passed,
                        compliant=evaluation.compliant,
                        strategy_digest=digest,
                        behavior_digest=evaluation.behavior_digest,
                    )
                )
    observed_miners = {item.miner_id for item in observations}
    for index in range(MINER_COUNT):
        miner_id = f"miner-{index:02}"
        if miner_id not in observed_miners:
            observations.append(
                EpochObservation(
                    miner_id=miner_id,
                    epoch=record["epoch"],
                    family=record["family"],
                    task_id=task.public.task_id,
                    task_commitment=task.public.commitment,
                    evidence_digest=domain_separated_digest(
                        "planrace/2:unavailable-evidence",
                        {"task": task.public.commitment, "miner": miner_id},
                    ),
                    reward=0.0,
                    available=False,
                    correct=False,
                    compliant=False,
                    strategy_digest=domain_separated_digest(
                        "planrace/2:unavailable-strategy", {"miner": miner_id}
                    ),
                    behavior_digest=domain_separated_digest(
                        "planrace/2:unavailable-behavior", {"miner": miner_id}
                    ),
                )
            )
    epoch_payload = {
        **record,
        "task_reveal": task.reveal.model_dump(mode="json"),
        "reveal_verified": reveal_verified,
        "strategy_evaluations": strategy_evaluations,
        "observations": [asdict(item) for item in sorted(observations, key=lambda x: x.miner_id)],
    }
    return epoch_payload, observations


def _evaluation_json(evaluation: Any) -> dict[str, Any]:
    return {
        "task_id": evaluation.task_id,
        "task_commitment": evaluation.task_commitment,
        "artifact_digest": evaluation.artifact_digest,
        "strategy_digest": evaluation.strategy_digest,
        "family_id": evaluation.family_id,
        "exact_passed": evaluation.exact_passed,
        "compliant": evaluation.compliant,
        "eligible": evaluation.eligible,
        "reward": evaluation.reward,
        "failure_code": evaluation.failure_code,
        "fixtures": [
            {
                "fixture_id": fixture.fixture_id,
                "result": fixture.result.model_dump(mode="json"),
                "score": asdict(fixture.score),
            }
            for fixture in evaluation.fixture_evaluations
        ],
    }


def _validator_rank_analysis(epoch_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    scores: dict[int, dict[str, list[float]]] = {
        index: defaultdict(list) for index in range(VALIDATOR_COUNT)
    }
    for epoch in epoch_payloads:
        validator_index = int(epoch["validator_index"])
        for observation in epoch["observations"]:
            profile = PROFILE_NAMES[int(observation["miner_id"].split("-")[1])]
            scores[validator_index][profile].append(float(observation["reward"]))
    means = {
        str(index): {
            profile: statistics.fmean(values) if values else 0.0
            for profile, values in score_map.items()
        }
        for index, score_map in scores.items()
    }
    correlations = [
        {
            "left": left,
            "right": right,
            "kendall_tau_b": kendall_tau_b(means[str(left)], means[str(right)]),
        }
        for left in range(VALIDATOR_COUNT)
        for right in range(left + 1, VALIDATOR_COUNT)
    ]
    return {"mean_rewards": means, "pairwise": correlations}


def _submit_final_weights(
    allocation: Any, *, netuid: int, wallet_path: Path
) -> tuple[dict[str, Any] | None, dict[str, Any], list[tuple[int, int]]]:
    subtensor = bt.Subtensor("local")
    wallet = bt.Wallet(name="planrace-v2-dev", hotkey="validator0", path=str(wallet_path))
    planned = dict(allocation.weights)
    uid_weights = [
        (index + 3, planned.get(f"miner-{index:02}", 0.0)) for index in range(MINER_COUNT)
    ]
    positive = [(uid, weight) for uid, weight in uid_weights if weight > 0.0]
    extrinsic: dict[str, Any] | None = None
    submitted: list[tuple[int, int]] = []
    if allocation.planned and positive:
        uids, values = normalize([uid for uid, _ in positive], [weight for _, weight in positive])
        submitted = list(zip(uids, values, strict=True))
        result = subtensor.submit_call(  # type: ignore[no-untyped-call]
            calls.SubtensorModule.set_mechanism_weights(
                netuid=netuid,
                mecid=0,
                dests=uids,
                weights=values,
                version_key=0,
            ),
            wallet,
            signer="hotkey",
            period=None,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
        extrinsic = {
            "success": result.success,
            "message": result.message,
            "error": str(result.error) if result.error else None,
            "extrinsic_id": result.extrinsic_id,
            "block_hash": result.block_hash,
            "fee_tao": float(getattr(result.fee, "tao", 0.0)),
        }
    metagraph = subtensor.read("metagraph", netuid=netuid)
    readback = subtensor.read("weights", netuid=netuid, mechid=0)
    runtime_spec_version = subtensor.spec_version
    subtensor.close()
    return (
        extrinsic,
        {
            "runtime_spec_version": runtime_spec_version,
            "metagraph": metagraph,
            "weights": readback,
        },
        submitted,
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(_canonical_bytes(value) + b"\n")
    temporary.replace(path)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read checkpoint {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"checkpoint must contain a JSON object: {path}")
    return value


def _write_run_input(
    path: Path,
    *,
    started_at: str,
    epochs: int,
    worker_image: str,
    dispatches: list[dict[str, Any]],
    tasks: list[PrivateTaskV2],
) -> None:
    _write_json(
        path,
        {
            "schema_version": "planrace/localnet-v2-input/1",
            "started_at": started_at,
            "epochs": epochs,
            "worker_image": worker_image,
            "dispatches": dispatches,
            "tasks": [
                {
                    "public": task.public.model_dump(mode="json"),
                    "reveal": task.reveal.model_dump(mode="json"),
                }
                for task in tasks
            ],
        },
    )


def _load_run_input(
    path: Path,
    *,
    epochs: int,
    worker_image: str,
) -> tuple[str, list[dict[str, Any]], list[PrivateTaskV2]]:
    value = _read_json_object(path)
    if value.get("schema_version") != "planrace/localnet-v2-input/1":
        raise RuntimeError("unsupported localnet run-input schema")
    if value.get("epochs") != epochs:
        raise RuntimeError("run-input epoch count does not match --epochs")
    if value.get("worker_image") != worker_image:
        raise RuntimeError("run-input worker image does not match --worker-image")
    raw_dispatches = value.get("dispatches")
    raw_tasks = value.get("tasks")
    if not isinstance(raw_dispatches, list) or not isinstance(raw_tasks, list):
        raise RuntimeError("run-input dispatches and tasks must be arrays")
    if len(raw_dispatches) != epochs or len(raw_tasks) != epochs:
        raise RuntimeError("run-input does not contain the requested number of epochs")

    dispatches: list[dict[str, Any]] = []
    tasks: list[PrivateTaskV2] = []
    for epoch, (raw_dispatch, raw_task) in enumerate(zip(raw_dispatches, raw_tasks, strict=True)):
        if not isinstance(raw_dispatch, dict) or not isinstance(raw_task, dict):
            raise RuntimeError(f"run-input epoch {epoch} must contain JSON objects")
        if raw_dispatch.get("epoch") != epoch:
            raise RuntimeError(f"run-input dispatch sequence differs at epoch {epoch}")
        public = PublicTaskV2.model_validate_json(
            json.dumps(raw_task.get("public"), separators=(",", ":"))
        )
        reveal = TaskRevealV2.model_validate_json(
            json.dumps(raw_task.get("reveal"), separators=(",", ":"))
        )
        if raw_dispatch.get("task_public") != public.model_dump(mode="json"):
            raise RuntimeError(f"run-input public task differs at epoch {epoch}")
        dispatches.append(dict(raw_dispatch))
        tasks.append(PrivateTaskV2(public=public, reveal=reveal))

    started_at = value.get("started_at")
    if not isinstance(started_at, str) or not started_at:
        raise RuntimeError("run-input started_at is missing")
    return started_at, dispatches, tasks


def _load_epoch_checkpoint(
    path: Path,
    *,
    record: dict[str, Any],
    task: PrivateTaskV2,
) -> tuple[dict[str, Any], list[EpochObservation]]:
    payload = _read_json_object(path)
    epoch = int(record["epoch"])
    if payload.get("epoch") != epoch:
        raise RuntimeError(f"checkpoint epoch differs for epoch {epoch}")
    if payload.get("task_public") != record.get("task_public"):
        raise RuntimeError(f"checkpoint public task differs for epoch {epoch}")
    if payload.get("task_reveal") != task.reveal.model_dump(mode="json"):
        raise RuntimeError(f"checkpoint reveal differs for epoch {epoch}")
    if payload.get("reveal_verified") is not True:
        raise RuntimeError(f"checkpoint reveal is not verified for epoch {epoch}")
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list):
        raise RuntimeError(f"checkpoint observations are missing for epoch {epoch}")
    observations = [
        EpochObservation(**observation)
        for observation in raw_observations
        if isinstance(observation, dict)
    ]
    if len(observations) != MINER_COUNT or len(observations) != len(raw_observations):
        raise RuntimeError(f"checkpoint observations are incomplete for epoch {epoch}")
    return payload, observations


def _set_chain_container_paused(name: str, *, paused: bool) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker executable is required")
    inspection = subprocess.run(  # noqa: S603 - fixed local Docker inspection argv
        [docker, "inspect", "--format", "{{.State.Status}} {{.State.Paused}}", name],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    try:
        status, paused_text = inspection.split()
    except ValueError as error:
        raise RuntimeError("unexpected local chain container state") from error
    if status not in {"running", "paused"}:
        raise RuntimeError(f"local chain container is not running: {status}")
    currently_paused = paused_text == "true"
    if currently_paused == paused:
        return
    subprocess.run(  # noqa: S603 - fixed operator-selected local container argv
        [docker, "pause" if paused else "unpause", name],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--netuid", type=int, default=3)
    parser.add_argument("--base-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--worker-image", required=True)
    parser.add_argument("--output", type=Path, default=Path("results/localnet-v2"))
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume evaluation from a previously written run-input and epoch checkpoints",
    )
    parser.add_argument("--evaluation-workers", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--chain-container", default="planrace-local-subtensor")
    parser.add_argument(
        "--pause-chain-during-evaluation",
        action="store_true",
        help=(
            "pause the local Subtensor container during worker timing; disabled by "
            "default because pausing a busy container can destabilize Docker Desktop"
        ),
    )
    arguments = parser.parse_args()
    if arguments.epochs < 30:
        raise SystemExit("localnet v2 evidence requires at least 30 epochs")
    if not arguments.worker_image.startswith("sha256:"):
        raise SystemExit("local evidence requires an immutable local image ID")
    run_input_path = arguments.output / "run-input.json"
    if arguments.resume:
        if (arguments.output / "manifest.json").exists():
            raise SystemExit("refusing to resume a completed evidence directory")
        if not run_input_path.is_file():
            raise SystemExit(f"resume requires an existing run input: {run_input_path}")
    elif arguments.output.exists() and any(arguments.output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty evidence directory: {arguments.output}")
    arguments.output.mkdir(parents=True, exist_ok=True)

    validators, miners = _public_identities()
    if arguments.resume:
        started_at, dispatches, tasks = _load_run_input(
            run_input_path,
            epochs=arguments.epochs,
            worker_image=arguments.worker_image,
        )
        print(f"resume loaded epochs={len(tasks)} from {run_input_path}", flush=True)
    else:
        processes = _start_miners(arguments.base_port, arguments.output)
        started_at = _utc_now()
        try:
            asyncio.run(_wait_for_miners(arguments.base_port, processes))
            dispatches, tasks = asyncio.run(
                _dispatch_epochs(
                    epochs=arguments.epochs,
                    base_port=arguments.base_port,
                    image_digest=arguments.worker_image,
                    validators=validators,
                    miners=miners,
                )
            )
        finally:
            _stop_miners(processes)
        _write_run_input(
            run_input_path,
            started_at=started_at,
            epochs=arguments.epochs,
            worker_image=arguments.worker_image,
            dispatches=dispatches,
            tasks=tasks,
        )
        print(f"checkpointed run input after all task deadlines: {run_input_path}", flush=True)

    def evaluate(
        pair: tuple[dict[str, Any], PrivateTaskV2],
    ) -> tuple[dict[str, Any], list[EpochObservation]]:
        record, task = pair
        epoch = int(record["epoch"])
        checkpoint = arguments.output / "checkpoints" / f"epoch-{epoch:03}.json"
        if checkpoint.is_file():
            loaded = _load_epoch_checkpoint(checkpoint, record=record, task=task)
            print(f"checkpoint epoch={epoch:02} loaded", flush=True)
            return loaded
        evaluated_epoch = _evaluate_epoch(record, task, image_digest=arguments.worker_image)
        _write_json(checkpoint, evaluated_epoch[0])
        print(f"checkpoint epoch={epoch:02} written", flush=True)
        return evaluated_epoch

    if arguments.pause_chain_during_evaluation:
        _set_chain_container_paused(arguments.chain_container, paused=True)
    try:
        with ThreadPoolExecutor(max_workers=arguments.evaluation_workers) as executor:
            evaluated = list(executor.map(evaluate, zip(dispatches, tasks, strict=True)))
    finally:
        if arguments.pause_chain_during_evaluation:
            _set_chain_container_paused(arguments.chain_container, paused=False)

    failed_batches = [
        (int(payload["epoch"]), str(payload["batch_failure"]))
        for payload, _ in evaluated
        if "batch_failure" in payload
    ]
    if failed_batches:
        failures = ", ".join(f"epoch {epoch}: {failure}" for epoch, failure in failed_batches)
        raise RuntimeError(f"refusing partial evidence after sandbox failure: {failures}")

    all_observations: list[EpochObservation] = []
    epoch_payloads: list[dict[str, Any]] = []
    for payload, observations in evaluated:
        epoch_payloads.append(payload)
        all_observations.extend(observations)
        epoch = int(payload["epoch"])
        _write_json(arguments.output / "epochs" / f"epoch-{epoch:03}.json", payload)
        print(
            f"evaluate epoch={epoch:02} unique={len(payload['strategy_evaluations'])}",
            flush=True,
        )

    families = tuple(family.family_id for family in QUERY_FAMILIES)
    schedule = tuple(
        ScheduledTask(
            epoch=payload["epoch"],
            family=payload["family"],
            task_id=payload["task_public"]["task_id"],
            task_commitment=payload["task_public"]["commitment"],
        )
        for payload in epoch_payloads
    )
    policy = AggregationPolicy(
        required_families=families,
        task_schedule=schedule,
        minimum_tasks=24,
        minimum_tasks_per_family=3,
        minimum_availability=0.75,
        minimum_compliance=0.95,
        minimum_correctness=0.95,
        maximum_weight=0.25,
        # Four independent groups are the minimum compatible with the 25% cap.
        minimum_distinct_strategies=4,
    )
    miner_ids = [f"miner-{index:02}" for index in range(MINER_COUNT)]
    aggregates = aggregate_network(all_observations, miner_ids=miner_ids, policy=policy)
    allocation = allocate_weights(aggregates, policy=policy)
    rank_analysis = _validator_rank_analysis(epoch_payloads)
    extrinsic, readback, submitted = _submit_final_weights(
        allocation,
        netuid=arguments.netuid,
        wallet_path=Path(".localnet-state/wallets"),
    )
    observed_at = _utc_now()
    summary = {
        "schema_version": "planrace/localnet-v2-run/1",
        "environment": "localnet",
        "network": "local",
        "runtime_spec_version": readback["runtime_spec_version"],
        "sdk_version": bt.__version__,
        "netuid": arguments.netuid,
        "run_id": f"localnet-v2-{int(time.time())}",
        "protocol_version": "planrace/2",
        "git_commit": _git_commit(),
        "worker_image": arguments.worker_image,
        "started_at": started_at,
        "observed_at": observed_at,
        "operator_model": "three test validator identities under one operator",
        "validators": [
            {"uid": index, "hotkey": key.ss58_address} for index, key in enumerate(validators)
        ],
        "miners": [
            {"uid": index + 3, "hotkey": key.ss58_address, "profile": PROFILE_NAMES[index]}
            for index, key in enumerate(miners)
        ],
        "epoch_count": arguments.epochs,
        "evaluation_workers": arguments.evaluation_workers,
        "chain_paused_during_evaluation": arguments.pause_chain_during_evaluation,
        "families": list(families),
        "aggregation_policy": {
            "minimum_tasks": policy.minimum_tasks,
            "minimum_tasks_per_family": policy.minimum_tasks_per_family,
            "minimum_availability": policy.minimum_availability,
            "minimum_compliance": policy.minimum_compliance,
            "minimum_correctness": policy.minimum_correctness,
            "maximum_weight": policy.maximum_weight,
            "minimum_distinct_strategies": policy.minimum_distinct_strategies,
        },
        "aggregates": [asdict(item) for item in aggregates],
        "allocation": asdict(allocation),
        "validator_rank_analysis": rank_analysis,
        "chain_extrinsic": extrinsic,
        "submitted_u16_weights": submitted,
        "chain_readback": readback,
        "known_limitations": [
            "All three validator identities ran on one machine under one operator.",
            (
                "The worker is identified by a local Docker content ID, not a "
                "published registry digest."
            ),
            (
                "Localnet commit-reveal was disabled with the public development sudo "
                "key because the local drand service was unavailable."
            ),
            (
                "Future-block entropy mixing is deferred; tasks use independent OS CSPRNG "
                "seeds and post-deadline reveal."
            ),
            *(
                []
                if arguments.pause_chain_during_evaluation
                else [
                    (
                        "The local Subtensor remained active during measurement; paired "
                        "same-worker baseline ratios reduce, but do not eliminate, shared "
                        "host noise."
                    )
                ]
            ),
            "Testnet evidence remains pending and is not implied by this localnet run.",
        ],
    }
    _write_json(arguments.output / "summary.json", summary)

    request_digests = tuple(
        outcome["request_digest"].removeprefix("sha256:")
        for epoch in epoch_payloads
        for outcome in epoch["outcomes"]
    )
    response_digests = tuple(
        domain_separated_digest(
            "planrace/2:signed-response-evidence", outcome["response"]
        ).removeprefix("sha256:")
        for epoch in epoch_payloads
        for outcome in epoch["outcomes"]
        if outcome["response"] is not None
    )
    schedule_digest = _sha256_bytes(
        _canonical_bytes([payload["task_public"]["commitment"] for payload in epoch_payloads])
    )
    reveal_digest = _sha256_bytes(
        _canonical_bytes([payload["task_reveal"] for payload in epoch_payloads])
    )
    submitted_map = dict(submitted)
    manifest_unsigned = {
        "schema_version": "planrace/evidence/2",
        "environment": "localnet",
        "network": "local",
        "netuid": arguments.netuid,
        "run_id": summary["run_id"],
        "epoch": arguments.epochs - 1,
        "git_commit": summary["git_commit"],
        "container_digests": {
            "validator_worker_local_content_id": arguments.worker_image.removeprefix("sha256:")
        },
        "protocol_version": "planrace/2",
        "validator_hotkeys": tuple(key.ss58_address for key in validators),
        "miner_hotkeys": tuple(key.ss58_address for key in miners),
        "task_commitment": schedule_digest,
        "task_reveal": {
            "task_id": "30-epoch-closed-schedule",
            "seed": None,
            "salt": "per-task independent 256-bit CSPRNG salts; see epoch evidence",
            "reveal_digest": reveal_digest,
            "verified": True,
        },
        "request_digests": request_digests,
        "response_digests": response_digests,
        "authentication": {
            "authenticated_requests": len(request_digests),
            "signed_responses": len(response_digests),
            "request_protocol": "Bittensor HTTP auth v1 + planrace/2 body",
            "response_protocol": "planrace/2 sr25519 miner signature",
        },
        "scores": tuple(
            {
                "uid": index + 3,
                "miner_hotkey": miners[index].ss58_address,
                "profile": PROFILE_NAMES[index],
                "accepted": aggregate.task_count > 0,
                "correct": aggregate.correctness >= 0.95,
                "score": aggregate.reward,
                "failure_code": aggregate.failure_code,
                "result_hash": None,
                "reference_hash": None,
                "strategy_digest": aggregate.strategy_digest.removeprefix("sha256:"),
                "schedule_digest": schedule_digest,
                "median_warm_ms": None,
                "setup_ms": None,
                "plan_cost": None,
                "baseline_relative_speedup": None,
            }
            for index, aggregate in enumerate(aggregates)
        ),
        "weight_plan": {
            "uids": tuple(uid for uid, _ in submitted),
            "weights": tuple((value / math.fsum(submitted_map.values())) for _, value in submitted),
        },
        "extrinsics": (
            ()
            if extrinsic is None
            else (
                {
                    "extrinsic_id": extrinsic["extrinsic_id"],
                    "block_hash": extrinsic["block_hash"].removeprefix("0x"),
                    "success": extrinsic["success"],
                    "message": extrinsic["message"],
                    "fee_tao": extrinsic["fee_tao"],
                },
            )
        ),
        "readback": {
            "validator_uid": 0,
            "last_update": int(readback["metagraph"]["last_update"][0]),
            "raw_weights": tuple(submitted),
        },
        "timestamps": {"observed_at": observed_at, "signed_at": _utc_now()},
        "known_limitations": tuple(summary["known_limitations"]),
        "source_artifacts": tuple(
            [
                {
                    "path": "summary.json",
                    "sha256": _sha256_bytes((arguments.output / "summary.json").read_bytes()),
                }
            ]
            + [
                {
                    "path": f"epochs/epoch-{epoch:03}.json",
                    "sha256": _sha256_bytes(
                        (arguments.output / "epochs" / f"epoch-{epoch:03}.json").read_bytes()
                    ),
                }
                for epoch in range(arguments.epochs)
            ]
        ),
    }
    signed = sign_manifest(manifest_unsigned, validators[0])
    _write_json(arguments.output / "manifest.json", signed.model_dump(mode="json"))
    print(json.dumps({"summary": summary, "manifest": "manifest.json"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
