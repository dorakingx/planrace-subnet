"""PlanRace command-line entry points."""

from __future__ import annotations

import json

import typer

from planrace.simulation import simulate

app = typer.Typer(no_args_is_help=True, help="PlanRace verified query optimizer subnet")


@app.callback()
def main() -> None:
    """Run PlanRace tools."""


@app.command("simulate")
def simulate_command(epochs: int = typer.Option(5, min=1, max=100)) -> None:
    """Run a deterministic multi-epoch local mechanism demo."""
    typer.echo(json.dumps(simulate(epochs), indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
