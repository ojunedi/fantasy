.PHONY: test lint backtest run-week propose-trades install clean

UV := $(HOME)/.local/bin/uv

install:
	$(UV) sync

test:
	$(UV) run pytest tests/ -v --tb=short

test-core:
	$(UV) run pytest tests/core/ -v --tb=short

lint:
	$(UV) run python -m py_compile src/fantasy_gm/models.py src/fantasy_gm/core/*.py src/fantasy_gm/adapters/*.py src/fantasy_gm/eval/*.py src/fantasy_gm/db/*.py src/fantasy_gm/signals/*.py src/fantasy_gm/signals/sources/*.py src/fantasy_gm/agent/*.py src/fantasy_gm/agent/subagents/*.py src/fantasy_gm/agent/trade/*.py src/fantasy_gm/execute/*.py src/fantasy_gm/memo/*.py
	@echo "Syntax OK"

backtest:
	$(UV) run python -m fantasy_gm.cli backtest --season $(or $(SEASON),2024) --weeks $(or $(WEEKS),1-14)

run-week:
	$(UV) run python -m fantasy_gm.cli run-week --week $(or $(WEEK),1) --season $(or $(SEASON),2025)

propose-trades:
	$(UV) run python -m fantasy_gm.cli propose-trades --week $(or $(WEEK),1) --season $(or $(SEASON),2026)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
