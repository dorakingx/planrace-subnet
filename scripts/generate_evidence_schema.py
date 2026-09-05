#!/usr/bin/env python3
"""Regenerate the checked-in current EvidenceManifest JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

from planrace.evidence import EvidenceManifest


def main() -> None:
    output = Path("schemas/evidence-manifest-v2.schema.json")
    output.write_text(
        json.dumps(EvidenceManifest.model_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
