#!/usr/bin/env python3
"""Generate the committed PlanRace v2 mechanism evidence bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from planrace.mechanism_simulation import (
    SimulationConfig,
    run_mechanism_simulation,
    write_evidence_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replications", type=int, default=512)
    parser.add_argument("--epochs", type=int, default=24)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20_260_901)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/mechanism-v2"),
    )
    arguments = parser.parse_args()
    if arguments.replications < 500:
        parser.error("published mechanism evidence requires at least 500 replications")
    if arguments.epochs < 24:
        parser.error("published mechanism evidence requires at least 24 epochs")
    config = SimulationConfig(
        replications=arguments.replications,
        epochs=arguments.epochs,
        trials_per_task=arguments.trials,
        root_seed=arguments.seed,
    )
    report = run_mechanism_simulation(config)
    manifest = write_evidence_bundle(report, arguments.output)
    summary = report["summary"]
    print(
        f"wrote {summary['replications']} replications to {arguments.output}; "
        f"FAR={summary['false_acceptance_rate']:.6f}; "
        f"manifest={manifest['config_sha256'][:12]}"
    )


if __name__ == "__main__":
    main()
