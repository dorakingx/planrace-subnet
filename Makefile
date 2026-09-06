UV := .bootstrap/bin/uv

.PHONY: help bootstrap sync test lint typecheck audit verify evidence-verify demo testnet-preflight local-epoch localnet-v2-audit mechanism-v2 mechanism-v2-audit secrets

help:
	@echo "PlanRace developer commands"
	@echo "  make bootstrap           install the pinned Python environment"
	@echo "  make verify              code checks plus full committed-evidence audit"
	@echo "  make evidence-verify     reproduce and audit committed evidence"
	@echo "  make demo                run a small protocol-v2 mechanism demo"
	@echo "  make testnet-preflight   run the transaction-free testnet connectivity check"
	@echo "  make localnet-v2-audit   audit committed localnet evidence"
	@echo "  make mechanism-v2-audit  reproduce and audit mechanism evidence"

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
	$(UV) run detect-secrets-hook --baseline .secrets.baseline $$(git ls-files)

verify: lint typecheck test secrets evidence-verify

evidence-verify: mechanism-v2-audit localnet-v2-audit

demo:
	@$(UV) run planrace simulate-v2

testnet-preflight:
	@$(UV) run planrace testnet preflight

local-epoch:
	@$(UV) run python scripts/run_local_epoch.py --epoch 8

localnet-v2-audit:
	@$(UV) run python scripts/audit_localnet_v2.py results/localnet-v2

mechanism-v2:
	@$(UV) run python scripts/run_mechanism_v2.py

mechanism-v2-audit:
	@$(UV) run python scripts/verify_mechanism_v2.py --require-clean-source
