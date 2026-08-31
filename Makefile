UV := .bootstrap/bin/uv

.PHONY: bootstrap sync test lint typecheck audit verify demo local-epoch secrets

bootstrap:
	./scripts/bootstrap.sh

sync:
	$(UV) sync --all-groups

test:
	$(UV) run pytest --cov=planrace --cov-report=term-missing

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy planrace

audit:
	$(UV) run pip-audit

secrets:
	$(UV) run detect-secrets scan --all-files --exclude-files '(^uv\.lock$$|^\.git/)' >/dev/null

verify: lint typecheck test secrets

demo:
	@$(UV) run planrace simulate --epochs 5

local-epoch:
	@$(UV) run python scripts/run_local_epoch.py --epoch 8
