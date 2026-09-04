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
from planrace.simulation import simulate

app = typer.Typer(no_args_is_help=True, help="PlanRace verified query optimizer subnet")
evidence_app = typer.Typer(no_args_is_help=True, help="Verify signed PlanRace run evidence")
app.add_typer(evidence_app, name="evidence")


@app.callback()
def main() -> None:
    """Run PlanRace tools."""


@app.command("simulate")
def simulate_command(epochs: int = typer.Option(5, min=1, max=100)) -> None:
    """Run a deterministic multi-epoch local mechanism demo."""
    typer.echo(json.dumps(simulate(epochs), indent=2, sort_keys=True))


def _verified_evidence(path: Path) -> tuple[EvidenceManifest, str]:
    try:
        return verify_manifest_file(path)
    except EvidenceVerificationError as error:
        typer.echo(f"INVALID: {error}", err=True)
        raise typer.Exit(code=1) from error


@evidence_app.command("verify")
def verify_evidence_command(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Verify a signed EvidenceManifest and reject any tampering."""

    evidence, digest = _verified_evidence(manifest)
    typer.echo(
        f"VERIFIED {evidence.run_id} sha256:{digest} "
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
