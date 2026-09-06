#!/usr/bin/env python3
"""Audit and optionally seal a completed PlanRace v2 localnet evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import bittensor as bt

from planrace.auth_v2 import optimization_response_signing_bytes
from planrace.benchmark_v2 import generate_hidden_fixtures
from planrace.evidence import sign_manifest, verify_manifest_file
from planrace.models_v2 import (
    OptimizationRequestV2,
    PublicTaskV2,
    SignedOptimizationResponse,
    TaskRevealV2,
    domain_separated_digest,
    optimization_request_digest,
    optimization_strategy_digest,
)
from planrace.scoring_v2 import (
    AggregationPolicy,
    EpochObservation,
    ScheduledTask,
    aggregate_network,
    allocate_weights,
)
from planrace.taskgen_v2 import audit_task_reveal


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _readback_matches(
    readback: dict[str, Any], submitted: list[list[int]], *, validator_uid: int = 0
) -> bool:
    validator_weights = readback.get(str(validator_uid), readback.get(validator_uid))
    if not isinstance(validator_weights, dict) or not submitted:
        return False
    raw = {int(uid): int(weight) for uid, weight in submitted}
    actual = {int(uid): float(weight) for uid, weight in validator_weights.items()}
    if raw.keys() != actual.keys() or any(weight <= 0 for weight in raw.values()):
        return False
    total = math.fsum(raw.values())
    tolerance = 2.0 / 65_535.0
    return math.isclose(math.fsum(actual.values()), 1.0, abs_tol=tolerance) and all(
        math.isclose(actual[uid], weight / total, abs_tol=tolerance) for uid, weight in raw.items()
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _committed_generator_digest(commit: str) -> str:
    """Hash the exact generator source named by the signed evidence."""

    _require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "invalid evidence source commit")
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable is required for source verification")
    try:
        source = subprocess.run(  # noqa: S603 - commit is restricted to a full hex SHA
            [git, "show", f"{commit}:planrace/benchmark_v2.py"],
            check=True,
            capture_output=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"cannot read generator source from commit {commit}") from error
    version_match = re.search(rb'^GENERATOR_VERSION: Final = "([^"\r\n]+)"$', source, re.MULTILINE)
    if version_match is None:
        raise RuntimeError("generator version missing from committed source")
    payload = b"planrace/2:benchmark-generator\x00" + version_match.group(1) + b"\x00" + source
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _audit_portable_fixture_regeneration(
    claimed: tuple[Any, ...], regenerated: tuple[Any, ...], path: Path
) -> None:
    """Compare logical fixture identity without assuming identical SQLite bytes.

    SQLite database files are checked byte-for-byte by the pinned evaluation
    worker. Their serialization is not stable across SQLite builds, so an
    independent host regenerates and compares the canonical logical digest,
    parameter digest, row count, and identity instead. The signed Merkle root
    and task commitment still bind each run's original database-file digest.
    """

    _require(len(claimed) == len(regenerated), f"regenerated fixture count mismatch: {path}")
    portable_fields = ("fixture_id", "content_digest", "parameter_set_digest", "row_count")
    for expected, actual in zip(claimed, regenerated, strict=True):
        _require(
            expected.database_file_digest is not None,
            f"committed database-file digest missing: {path}",
        )
        for field in portable_fields:
            _require(
                getattr(expected, field) == getattr(actual, field),
                f"regenerated fixture {field} mismatch: {path}",
            )


def audit_bundle(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    manifest_path = bundle / "manifest.json"
    manifest, original_digest = verify_manifest_file(manifest_path)
    for artifact in manifest.source_artifacts:
        artifact_path = (bundle / artifact.path).resolve()
        _require(
            artifact_path.is_relative_to(bundle),
            f"signed source artifact escapes evidence bundle: {artifact.path}",
        )
        _require(
            artifact_path.is_file() and _sha256(artifact_path) == artifact.sha256,
            f"signed source artifact mismatch: {artifact.path}",
        )
    summary = _load(bundle / "summary.json")
    epoch_paths = sorted((bundle / "epochs").glob("epoch-*.json"))

    _require(summary["protocol_version"] == "planrace/2", "wrong protocol")
    _require(manifest.schema_version == "planrace/evidence/2", "wrong evidence schema")
    _require(summary["environment"] == "localnet", "wrong environment")
    _require(
        summary["operator_model"] == "three test validator identities under one operator",
        "operator disclosure missing",
    )
    _require(summary["epoch_count"] >= 30, "fewer than 30 epochs")
    _require(len(epoch_paths) == summary["epoch_count"], "epoch file count mismatch")
    _require(
        len(manifest.source_artifacts) == len(epoch_paths) + 1,
        "manifest must bind the summary and every epoch file",
    )
    _require(len(summary["validators"]) == 3, "expected three validator identities")
    _require(len(summary["miners"]) == 10, "expected ten miner identities")
    _require(
        len({item["profile"] for item in summary["miners"]}) == 10, "profile labels are not unique"
    )
    miner_ids_by_profile = {
        item["profile"]: f"miner-{int(item['uid']) - 3:02}" for item in summary["miners"]
    }
    selective_id = miner_ids_by_profile["selective-index"]
    copycat_id = miner_ids_by_profile["copycat-sybil"]
    _require(manifest.netuid == summary["netuid"], "summary/manifest netuid mismatch")
    _require(
        list(manifest.validator_hotkeys) == [item["hotkey"] for item in summary["validators"]],
        "validator identity list mismatch",
    )
    _require(
        list(manifest.miner_hotkeys) == [item["hotkey"] for item in summary["miners"]],
        "miner identity list mismatch",
    )
    metagraph_hotkeys = summary["chain_readback"]["metagraph"]["hotkeys"]
    for identity in [*summary["validators"], *summary["miners"]]:
        _require(
            metagraph_hotkeys[identity["uid"]] == identity["hotkey"],
            f"metagraph hotkey mismatch at UID {identity['uid']}",
        )

    request_digests: list[str] = []
    response_digests: list[str] = []
    validator_counts: Counter[int] = Counter()
    families: set[str] = set()
    generator_digests: set[str] = set()
    accepted_responses = 0
    all_observations: list[EpochObservation] = []
    schedule: list[ScheduledTask] = []
    sybil_epochs = 0
    for expected_epoch, path in enumerate(epoch_paths):
        epoch = _load(path)
        _require(epoch["epoch"] == expected_epoch, f"epoch ordering mismatch: {path}")
        validator_counts[int(epoch["validator_index"])] += 1
        families.add(epoch["family"])
        public = PublicTaskV2.model_validate_json(json.dumps(epoch["task_public"]))
        reveal = TaskRevealV2.model_validate_json(json.dumps(epoch["task_reveal"]))
        regenerated = generate_hidden_fixtures(
            bytes.fromhex(reveal.secret_seed_hex),
            family_id=public.benchmark_family_id,
        )
        _require(
            audit_task_reveal(public, reveal),
            f"commitment/reveal failed: {path}",
        )
        _audit_portable_fixture_regeneration(
            reveal.hidden_fixtures,
            tuple(item.descriptor for item in regenerated),
            path,
        )
        generator_digests.add(public.generator_source_digest)
        _require(epoch["reveal_verified"] is True, f"reveal flag false: {path}")
        outcomes = epoch["outcomes"]
        _require(len(outcomes) == 10, f"outcome count mismatch: {path}")
        accepted = [item for item in outcomes if item["accepted"]]
        rejected = [item for item in outcomes if not item["accepted"]]
        _require(len(accepted) == 9, f"accepted response count mismatch: {path}")
        _require(
            [item["profile"] for item in rejected] == ["timeout-resource-attempt"],
            f"unexpected transport rejection: {path}",
        )
        expected_strategy_groups: dict[str, list[str]] = {}
        for item in accepted:
            response = SignedOptimizationResponse.model_validate_json(json.dumps(item["response"]))
            digest = optimization_strategy_digest(response.artifact)
            expected_strategy_groups.setdefault(digest, []).append(item["miner_id"])
        actual_strategy_groups = {
            digest: sorted(item["miners"]) for digest, item in epoch["strategy_evaluations"].items()
        }
        _require(
            6 <= len(actual_strategy_groups) <= len(accepted),
            f"strategy diversity outside expected bounds: {path}",
        )
        _require(
            actual_strategy_groups
            == {digest: sorted(miners) for digest, miners in expected_strategy_groups.items()},
            f"strategy evaluation grouping mismatch: {path}",
        )
        _require(len(epoch["observations"]) == 10, f"observation count mismatch: {path}")
        observations = [EpochObservation(**item) for item in epoch["observations"]]
        observations_by_miner = {item.miner_id: item for item in observations}
        selective_observation = observations_by_miner[selective_id]
        copycat_observation = observations_by_miner[copycat_id]
        if (
            selective_observation.strategy_digest == copycat_observation.strategy_digest
            and selective_observation.behavior_digest == copycat_observation.behavior_digest
            and selective_observation.evidence_digest == copycat_observation.evidence_digest
            and selective_observation.reward == copycat_observation.reward
        ):
            sybil_epochs += 1
        all_observations.extend(observations)
        schedule.append(
            ScheduledTask(
                epoch=epoch["epoch"],
                family=epoch["family"],
                task_id=epoch["task_public"]["task_id"],
                task_commitment=epoch["task_public"]["commitment"],
            )
        )
        accepted_responses += len(accepted)

        for outcome in outcomes:
            request = OptimizationRequestV2.model_validate_json(json.dumps(outcome["request"]))
            digest = optimization_request_digest(request)
            _require(digest == outcome["request_digest"], f"request digest mismatch: {path}")
            request_digests.append(digest.removeprefix("sha256:"))
            auth_headers = outcome["validator_auth_headers"]
            _require(
                any(name.startswith("x-bittensor-") for name in auth_headers),
                f"validator auth headers missing: {path}",
            )
            if outcome["response"] is None:
                continue
            response = SignedOptimizationResponse.model_validate_json(
                json.dumps(outcome["response"])
            )
            _require(
                response.request_digest == digest, f"response request binding mismatch: {path}"
            )
            _require(
                response.miner_hotkey == request.miner_hotkey, f"response miner mismatch: {path}"
            )
            _require(
                response.validator_hotkey == request.validator_hotkey,
                f"response validator mismatch: {path}",
            )
            verifier = bt.sp_core.Keypair(ss58_address=response.miner_hotkey)
            _require(
                verifier.verify(
                    optimization_response_signing_bytes(response),
                    bytes.fromhex(response.signature),
                ),
                f"miner response signature failed: {path}",
            )
            response_digests.append(
                domain_separated_digest(
                    "planrace/2:signed-response-evidence", outcome["response"]
                ).removeprefix("sha256:")
            )

    _require(validator_counts == Counter({0: 10, 1: 10, 2: 10}), "validator rotation mismatch")
    _require(
        sybil_epochs == len(epoch_paths),
        "copycat/Sybil pair was not grouped into one evaluation in every epoch",
    )
    _require(len(families) >= 4, "insufficient query-family coverage")
    _require(len(generator_digests) == 1, "multiple generator source digests in run")
    _require(
        generator_digests == {_committed_generator_digest(summary["git_commit"])},
        "evidence generator digest does not match its recorded source commit",
    )
    _require(request_digests == list(manifest.request_digests), "manifest request list mismatch")
    _require(response_digests == list(manifest.response_digests), "manifest response list mismatch")
    _require(
        manifest.authentication.authenticated_requests == len(request_digests),
        "manifest request count mismatch",
    )
    _require(
        manifest.authentication.signed_responses == accepted_responses,
        "manifest response count mismatch",
    )
    _require(
        all(
            score.result_hash is None
            and score.reference_hash is None
            and score.strategy_digest is not None
            and score.schedule_digest == manifest.task_commitment
            for score in manifest.scores
        ),
        "v2 score semantics are not explicit",
    )

    aggregation_policy = AggregationPolicy(
        required_families=tuple(summary["families"]),
        task_schedule=tuple(schedule),
        minimum_tasks=24,
        minimum_tasks_per_family=3,
        minimum_availability=0.75,
        minimum_compliance=0.95,
        minimum_correctness=0.95,
        maximum_weight=0.25,
        # Four independent groups are the minimum compatible with the 25% cap.
        minimum_distinct_strategies=4,
    )
    miner_ids = [f"miner-{index:02}" for index in range(10)]
    recomputed_aggregates = aggregate_network(
        all_observations, miner_ids=miner_ids, policy=aggregation_policy
    )
    recomputed_allocation = allocate_weights(recomputed_aggregates, policy=aggregation_policy)
    normalized_aggregates = json.loads(json.dumps([asdict(item) for item in recomputed_aggregates]))
    normalized_allocation = json.loads(json.dumps(asdict(recomputed_allocation)))
    _require(
        normalized_aggregates == summary["aggregates"],
        "stored aggregates do not match epoch observations",
    )
    _require(
        normalized_allocation == summary["allocation"],
        "stored behavior-group allocation does not recompute",
    )

    extrinsic = summary["chain_extrinsic"]
    _require(
        extrinsic is not None and extrinsic["success"] is True,
        "final chain extrinsic did not succeed",
    )
    _require(summary["allocation"]["planned"] is True, "allocation was not planned")
    strategy_weights = dict(summary["allocation"]["strategy_weights"])
    _require(len(strategy_weights) >= 4, "fewer than four eligible strategy portfolios")
    _require(
        math.isclose(math.fsum(strategy_weights.values()), 1.0, abs_tol=1e-12),
        "strategy allocations do not sum to one",
    )
    _require(
        max(strategy_weights.values()) <= 0.25 + 1e-12,
        "strategy concentration cap exceeded",
    )
    duplicate_groups = summary["allocation"]["duplicate_groups"]
    identity_weights = dict(summary["allocation"]["weights"])
    for digest, members in duplicate_groups:
        _require(
            math.isclose(
                math.fsum(identity_weights[member] for member in members),
                strategy_weights[digest],
                abs_tol=1e-12,
            ),
            "duplicate identity weights do not equal their strategy allocation",
        )
    if not any(len(members) > 1 for _, members in duplicate_groups):
        _require(
            identity_weights.get(selective_id, 0.0) == 0.0
            and identity_weights.get(copycat_id, 0.0) == 0.0,
            "ineligible copycat/Sybil identities received weight",
        )
    submitted = summary["submitted_u16_weights"]
    _require(bool(submitted), "empty submitted weight vector")
    _require(
        _readback_matches(summary["chain_readback"]["weights"], submitted),
        "submitted vector does not match normalized chain weight readback",
    )
    _require(
        list(manifest.readback.raw_weights) == [tuple(item) for item in submitted],
        "manifest raw weights mismatch",
    )
    _require(
        manifest.extrinsics and manifest.extrinsics[0].success,
        "manifest extrinsic is not successful",
    )
    _require(manifest.git_commit == summary["git_commit"], "summary/manifest git commit mismatch")

    source_artifacts = [
        {"path": "summary.json", "sha256": _sha256(bundle / "summary.json")},
        *[
            {
                "path": str(path.relative_to(bundle)),
                "sha256": _sha256(path),
            }
            for path in epoch_paths
        ],
    ]
    return {
        "manifest": manifest,
        "original_digest": original_digest,
        "source_artifacts": source_artifacts,
        "epoch_count": len(epoch_paths),
        "request_count": len(request_digests),
        "response_count": len(response_digests),
        "family_count": len(families),
        "extrinsic_id": extrinsic["extrinsic_id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path, nargs="?", default=Path("results/localnet-v2"))
    parser.add_argument(
        "--seal-source-artifacts",
        action="store_true",
        help="replace the source-artifact list with all audited files and re-sign",
    )
    args = parser.parse_args()
    result = audit_bundle(args.bundle)
    digest = result["original_digest"]
    if args.seal_source_artifacts:
        manifest = result["manifest"]
        unsigned = manifest.model_dump(mode="json", exclude={"validator_signature"})
        unsigned["source_artifacts"] = result["source_artifacts"]
        signer = bt.sp_core.Keypair.create_from_uri("//PlanRaceValidator0")
        _require(
            signer.ss58_address == manifest.validator_signature.signer_hotkey,
            "local development signer does not match manifest",
        )
        sealed = sign_manifest(unsigned, signer)
        (args.bundle / "manifest.json").write_text(
            json.dumps(
                sealed.model_dump(mode="json"),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        _, digest = verify_manifest_file(args.bundle / "manifest.json")
    print(
        json.dumps(
            {
                "status": "VERIFIED",
                "epochs": result["epoch_count"],
                "requests": result["request_count"],
                "signed_responses": result["response_count"],
                "families": result["family_count"],
                "extrinsic_id": result["extrinsic_id"],
                "manifest_sha256": digest,
                "all_epoch_files_signed": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
