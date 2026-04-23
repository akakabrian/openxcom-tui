VENDOR := engine/openxcom

.PHONY: all bootstrap venv run run-battle headless test test-only test-api perf clean

all: bootstrap venv

# One-shot fetch of the OpenXcom upstream (~80 MB). Used as a reference
# + ruleset YAML donor. We do NOT build the C++ engine here — see
# DECISIONS.md for rationale.
bootstrap: $(VENDOR)/.git
$(VENDOR)/.git:
	@echo "==> fetching OpenXcom upstream (~80 MB, one time)"
	@mkdir -p engine
	git clone --depth=1 https://github.com/OpenXcom/OpenXcom.git $(VENDOR)
	@echo "==> bootstrap complete"

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python openxcom.py

run-battle: venv
	.venv/bin/python openxcom.py --start-battle

headless: venv
	.venv/bin/python openxcom.py --headless --agent-port 8888

test: venv
	.venv/bin/python -m tests.qa

test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

test-api: venv
	.venv/bin/python -m tests.api_qa

perf: venv
	.venv/bin/python -m tests.perf

clean:
	rm -rf .venv openxcom_tui.egg-info __pycache__ */__pycache__ tests/out/*.svg
