UV := .bootstrap/bin/uv

.PHONY: bootstrap sync test lint typecheck audit verify demo local-epoch localnet-v2-audit mechanism-v2 mechanism-v2-audit secrets

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
	$(UV) run detect-secrets scan --all-files --exclude-files '(^uv\.lock$$|^\.git/|^dashboard/node_modules/|^dashboard/dist/)' >/dev/null

verify: lint typecheck test secrets

demo:
	@$(UV) run planrace simulate --epochs 5

local-epoch:
	@$(UV) run python scripts/run_local_epoch.py --epoch 8

localnet-v2-audit:
	@$(UV) run python scripts/audit_localnet_v2.py results/localnet-v2

mechanism-v2:
	@$(UV) run python scripts/run_mechanism_v2.py

mechanism-v2-audit:
	@$(UV) run python scripts/verify_mechanism_v2.py --require-clean-source
