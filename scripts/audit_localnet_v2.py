#!/usr/bin/env python3
"""Audit and optionally seal a completed PlanRace v2 localnet evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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
from planrace.taskgen_v2 import audit_task_reveal


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contains(value: Any, target: Any) -> bool:
    if value == target:
        return True
    if isinstance(value, dict):
        return any(_contains(item, target) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, target) for item in value)
    return False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def audit_bundle(bundle: Path) -> dict[str, Any]:
    manifest_path = bundle / "manifest.json"
    manifest, original_digest = verify_manifest_file(manifest_path)
    for artifact in manifest.source_artifacts:
        artifact_path = bundle / artifact.path
        _require(
            artifact_path.is_file() and _sha256(artifact_path) == artifact.sha256,
            f"signed source artifact mismatch: {artifact.path}",
        )
    summary = _load(bundle / "summary.json")
    epoch_paths = sorted((bundle / "epochs").glob("epoch-*.json"))

    _require(summary["protocol_version"] == "planrace/2", "wrong protocol")
    _require(summary["environment"] == "localnet", "wrong environment")
    _require(
        summary["operator_model"] == "three test validator identities under one operator",
        "operator disclosure missing",
    )
    _require(summary["epoch_count"] >= 30, "fewer than 30 epochs")
    _require(len(epoch_paths) == summary["epoch_count"], "epoch file count mismatch")
    _require(len(summary["validators"]) == 3, "expected three validator identities")
    _require(len(summary["miners"]) == 10, "expected ten miner identities")
    _require(
        len({item["profile"] for item in summary["miners"]}) == 10, "profile labels are not unique"
    )
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
    accepted_responses = 0
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
        regenerated_descriptors = tuple(item.descriptor for item in regenerated)
        _require(
            audit_task_reveal(
                public,
                reveal,
                regenerate=lambda _seed, expected=regenerated_descriptors: expected,
            ),
            f"commitment/reveal failed: {path}",
        )
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
    _require(len(families) >= 4, "insufficient query-family coverage")
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

    extrinsic = summary["chain_extrinsic"]
    _require(
        extrinsic is not None and extrinsic["success"] is True,
        "final chain extrinsic did not succeed",
    )
    _require(summary["allocation"]["planned"] is True, "allocation was not planned")
    submitted = summary["submitted_u16_weights"]
    _require(bool(submitted), "empty submitted weight vector")
    _require(
        _contains(summary["chain_readback"]["weights"], submitted),
        "submitted vector is absent from actual chain weight readback",
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
                "all_epoch_files_signed": args.seal_source_artifacts,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
