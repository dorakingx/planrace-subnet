#!/usr/bin/env python3
"""Verify the committed PlanRace v2 mechanism evidence bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from planrace.mechanism_simulation import verify_evidence_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path, nargs="?", default=Path("results/mechanism-v2"))
    parser.add_argument("--require-clean-source", action="store_true")
    arguments = parser.parse_args()
    manifest = verify_evidence_bundle(
        arguments.bundle,
        require_clean_source=arguments.require_clean_source,
    )
    print(
        json.dumps(
            {
                "status": "VERIFIED",
                "schema_version": manifest["schema_version"],
                "artifacts": len(manifest["artifacts"]),
                "config_sha256": manifest["config_sha256"],
                "source_git_base_commit": manifest["source_git_base_commit"],
                "source_tree_dirty": manifest["source_tree_dirty"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
