#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bootstrap_dir="${project_dir}/.bootstrap"

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "python3.12 is required" >&2
  exit 1
fi

if [[ ! -x "${bootstrap_dir}/bin/python" ]]; then
  python3.12 -m venv "${bootstrap_dir}"
fi

"${bootstrap_dir}/bin/python" -m pip install --disable-pip-version-check --quiet "uv==0.12.7"
"${bootstrap_dir}/bin/uv" --version
