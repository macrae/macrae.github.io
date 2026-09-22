# seanmacrae.com — the commands you actually need.
#
# `make site` must be HERMETIC: no network, no clock, no environment reads.
# `make migrate` is a separate target precisely so that property is structural
# rather than a promise in a comment.

PY   := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PORT ?= 8000

.DEFAULT_GOAL := help
.PHONY: help setup site validate test check serve preview migrate clean

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create .venv and install everything
	uv venv --python 3.12
	uv pip install -e ".[migrate,dev]"

site:  ## Render content/ into docs/   <-- THE GATE TARGET
	$(PY) -m sitegen.build

validate:  ## Check the rendered tree
	$(PY) -m sitegen.validate docs

test:  ## The suite
	$(PY) -m pytest $(PYTEST_ARGS)

check: site validate test  ## What to run before pushing

serve:  ## Serve the built site
	@echo "  http://localhost:$(PORT)/"
	@cd docs && python3 -m http.server $(PORT)

preview:  ## Build EVERYTHING including staged/archived, to preview/ — never deployed
	$(PY) -m sitegen.build --include-unpublished --out preview
	@echo ""
	@echo "  Staged posts included. This is the SAME renderer with a different"
	@echo "  filter, not a second code path — a renderer kept behind a flag is"
	@echo "  a renderer nobody is testing."
	@echo "  http://localhost:$(PORT)/   (cd preview && python3 -m http.server $(PORT))"

migrate:  ## One-shot WordPress capture + convert. NETWORKED; never in CI.
	$(PY) migrate/fetch_wp.py all
	$(PY) migrate/convert.py

clean:  ## Drop caches. Never touches docs/, content/ or archive/.
	rm -rf .pytest_cache preview
	find . -name __pycache__ -type d -not -path "./.venv/*" -exec rm -rf {} +
