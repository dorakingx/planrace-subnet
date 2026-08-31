#!/usr/bin/env python3
"""Run one signed PlanRace epoch against the public localnet dev identities.

This script is deliberately locked to Bittensor's local endpoint. The Alice,
Bob, and Charlie development keys are public and are never suitable for funds.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from typing import Any

import bittensor as bt
import httpx

from planrace.scoring import evaluate_artifact
from planrace.taskgen import generate_workload
from planrace.validator_client import request_optimization
from planrace.weights import plan_weights

MINERS = (
    (1, "honest", "http://127.0.0.1:8091/v1/optimize", "//Bob"),
    (2, "gaming", "http://127.0.0.1:8092/v1/optimize", "//Charlie"),
)


async def run_epoch(epoch: int) -> tuple[dict[str, Any], tuple[int, ...], tuple[float, ...]]:
    validator = bt.sp_core.Keypair.create_from_uri("//Alice")
    workload = generate_workload(epoch)
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for uid, profile, endpoint, miner_uri in MINERS:
            receiver = bt.sp_core.Keypair.create_from_uri(miner_uri).ss58_address
            outcome = await request_optimization(
                client,
                wallet=validator,
                endpoint=endpoint,
                receiver_ss58=receiver,
                task=workload.task,
            )
            if not outcome.accepted or outcome.artifact is None:
                results.append(
                    {
                        "uid": uid,
                        "profile": profile,
                        "accepted": False,
                        "failure_code": outcome.failure_code,
                    }
                )
                continue
            score = evaluate_artifact(workload, outcome.artifact)
            results.append(
                {
                    "uid": uid,
                    "profile": profile,
                    "accepted": True,
                    **score.model_dump(),
                }
            )

    plan = plan_weights({result["uid"]: result.get("score", 0.0) for result in results})
    report = {
        "network": "local",
        "task": workload.task.model_dump(),
        "results": results,
        "weight_plan": asdict(plan),
    }
    return report, plan.uids, plan.weights


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epoch", type=int, default=8)
    parser.add_argument("--netuid", type=int, default=2)
    parser.add_argument(
        "--submit-local-weights",
        action="store_true",
        help="submit the derived weights with public //Alice to localnet only",
    )
    args = parser.parse_args()
    report, uids, weights = await run_epoch(args.epoch)
    if args.submit_local_weights:
        subtensor = bt.Subtensor("local")
        try:
            result = subtensor.execute(
                bt.SetWeights(args.netuid, uids=list(uids), weights=list(weights)),
                bt.sp_core.Keypair.create_from_uri("//Alice"),
                period=None,
            )
            report["extrinsic"] = result.to_dict()
        finally:
            subtensor.close()
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
