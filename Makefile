# Agentic Motor Claims Platform — Allianz Austria demonstration build
.DEFAULT_GOAL := help
UV  := $(HOME)/.local/bin/uv
PY  := backend/.venv/bin/python
PORT_API ?= 8099
PORT_WEB ?= 5173

.PHONY: help install backend frontend dev test suite evals reset clean check

help: ## Show the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the Python venv, install both stacks
	$(UV) venv --python 3.12 backend/.venv
	$(UV) pip install --python $(PY) -r backend/requirements.txt
	cd frontend && npm install

backend: ## Run the API on $(PORT_API)
	cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port $(PORT_API)

frontend: ## Run the console on $(PORT_WEB)
	cd frontend && npm run dev

dev: ## Run both (API in the background, console in the foreground)
	cd backend && .venv/bin/python -m uvicorn app.main:app --port $(PORT_API) & \
	  sleep 2 && cd frontend && npm run dev

test: ## Run the zero-trust test suite
	cd backend && .venv/bin/python -m pytest tests -q

suite: ## Run the security regression suite against the running API
	@curl -s -X POST http://127.0.0.1:$(PORT_API)/api/security/regression \
	  | $(PY) -c "import json,sys;d=json.load(sys.stdin);print(f\"regression: {d['passed']}/{d['total']} ({d['pass_rate']*100:.0f}%)\")"

evals: ## Run the golden-case evaluations against the running API
	@curl -s -X POST http://127.0.0.1:$(PORT_API)/api/evals/run \
	  | $(PY) -c "import json,sys;d=json.load(sys.stdin);print(f\"evals: {d['passed']}/{d['cases']} cases, {d['assertions']['passed']}/{d['assertions']['total']} assertions\")"

reset: ## Return the demo data to a pristine state
	@curl -s -X POST http://127.0.0.1:$(PORT_API)/api/admin/reset > /dev/null && echo "demo data reset"

check: ## Typecheck the console and build it
	cd frontend && npx tsc -b --noEmit && npx vite build

clean: ## Remove the database and build output
	rm -f backend/claims.db
	rm -rf frontend/dist
