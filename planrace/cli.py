"""PlanRace command-line entry points."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from planrace.evidence import (
    EvidenceManifest,
    EvidenceVerificationError,
    summarize_manifest,
    verify_manifest_file,
)
from planrace.mechanism_simulation import SimulationConfig, run_mechanism_simulation
from planrace.simulation import simulate
from planrace.testnet_preflight import collect_testnet_preflight
from planrace.testnet_weights import collect_testnet_weight_plan

app = typer.Typer(no_args_is_help=True, help="PlanRace verified query optimizer subnet")
evidence_app = typer.Typer(no_args_is_help=True, help="Verify signed PlanRace run evidence")
testnet_app = typer.Typer(no_args_is_help=True, help="Read-only Bittensor testnet checks")
app.add_typer(evidence_app, name="evidence")
app.add_typer(testnet_app, name="testnet")


@app.callback()
def main() -> None:
    """Run PlanRace tools."""


@app.command("simulate")
def simulate_command(epochs: int = typer.Option(5, min=1, max=100)) -> None:
    """Run the preserved historical protocol-v1 simulation."""
    typer.echo(json.dumps(simulate(epochs), indent=2, sort_keys=True))


@app.command("simulate-v2")
def simulate_v2_command(
    replications: int = typer.Option(8, min=8, max=512),
    epochs: int = typer.Option(12, min=12, max=24),
) -> None:
    """Run a short deterministic protocol-v2 adversarial mechanism demo."""

    report = run_mechanism_simulation(
        SimulationConfig(replications=replications, epochs=epochs, trials_per_task=6)
    )
    typer.echo(json.dumps(report["summary"], indent=2, sort_keys=True))


@testnet_app.command("preflight")
def testnet_preflight_command(
    netuid: Annotated[int | None, typer.Option(min=0)] = None,
    coldkey_ss58: Annotated[
        str | None,
        typer.Option(help="Public dedicated testnet coldkey address; never a seed or private key."),
    ] = None,
    hotkey: Annotated[
        list[str] | None,
        typer.Option(help="Repeat public role=SS58 values, e.g. validator=5..."),
    ] = None,
    require_registered: bool = typer.Option(False),
    require_served_axon: bool = typer.Option(False),
) -> None:
    """Inspect one testnet block without constructing or signing transactions."""

    try:
        report = collect_testnet_preflight(
            netuid=netuid,
            coldkey_ss58=coldkey_ss58,
            role_specs=hotkey or (),
            require_registered=require_registered,
            require_served_axon=require_served_axon,
        )
    except ValueError as error:
        typer.echo(json.dumps({"error": str(error)}, sort_keys=True))
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    if (
        not report.chain_reachable
        or report.errors
        or not report.gates.registration_requirement_met
        or not report.gates.served_axon_requirement_met
    ):
        raise typer.Exit(code=1)


@testnet_app.command("weight-plan")
def testnet_weight_plan_command(
    netuid: Annotated[int, typer.Option(min=0)],
    validator_hotkey_ss58: Annotated[
        str,
        typer.Option(help="Public validator hotkey address; never a seed or private key."),
    ],
    score: Annotated[
        list[str] | None,
        typer.Option(help="Repeat public SS58=score values for miners."),
    ] = None,
    minimum_positive_hotkeys: Annotated[int, typer.Option(min=1)] = 2,
) -> None:
    """Plan and read back testnet weights without constructing a transaction."""

    try:
        report = collect_testnet_weight_plan(
            netuid=netuid,
            validator_hotkey_ss58=validator_hotkey_ss58,
            score_specs=score or (),
            minimum_positive_hotkeys=minimum_positive_hotkeys,
        )
    except ValueError as error:
        typer.echo(json.dumps({"error": str(error)}, sort_keys=True))
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    if report.errors or not report.ready_for_authorized_submission:
        raise typer.Exit(code=1)


def _verified_evidence(
    path: Path, *, expected_signer: str | None = None
) -> tuple[EvidenceManifest, str]:
    try:
        return verify_manifest_file(path, expected_signer=expected_signer)
    except EvidenceVerificationError as error:
        typer.echo(f"INVALID: {error}", err=True)
        raise typer.Exit(code=1) from error


@evidence_app.command("verify")
def verify_evidence_command(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    expected_signer: Annotated[
        str | None,
        typer.Option(help="Trusted validator hotkey expected to sign this manifest."),
    ] = None,
) -> None:
    """Verify manifest integrity; observational claims need external anchors."""

    evidence, digest = _verified_evidence(manifest, expected_signer=expected_signer)
    trust = "EXPECTED SIGNER" if expected_signer is not None else "CLAIMS UNVERIFIED"
    typer.echo(
        f"SIGNATURE VALID; {trust} {evidence.run_id} sha256:{digest} "
        f"signer:{evidence.validator_signature.signer_hotkey}"
    )


@evidence_app.command("summarize")
def summarize_evidence_command(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Verify an EvidenceManifest and print its headline metrics as JSON."""

    evidence, digest = _verified_evidence(manifest)
    typer.echo(json.dumps(summarize_manifest(evidence, digest), indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
