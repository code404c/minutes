UV := uv
PYTHON := $(UV) run python
PYTEST := $(UV) run pytest
RUFF := $(UV) run ruff
DOCKER_COMPOSE := docker compose

.PHONY: help check-env install db-upgrade dev-gateway dev-orchestrator dev-inference redis test format lint check smoke-fake smoke-real docker-up docker-down

help:
	@echo "开发:"
	@echo "  make install          - 同步依赖 (uv sync --extra dev)"
	@echo "  make db-upgrade       - 执行 Alembic 迁移"
	@echo "  make dev-gateway      - 启动 Gateway (热重载)"
	@echo "  make dev-orchestrator - 启动 Orchestrator worker"
	@echo "  make dev-inference    - 启动 Inference worker"
	@echo "  make redis            - 启动 Redis"
	@echo ""
	@echo "代码质量:"
	@echo "  make format           - ruff format"
	@echo "  make lint             - ruff check --fix"
	@echo "  make test             - pytest"
	@echo "  make check            - format-check + lint + test"
	@echo "  make check-env        - 环境自检"
	@echo ""
	@echo "Smoke:"
	@echo "  make smoke-fake AUDIO=/path/to/audio"
	@echo "  make smoke-real AUDIO=/path/to/audio"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up        - docker compose up --build"
	@echo "  make docker-down      - docker compose down"

check-env:
	python3 scripts/check_env.py

install:
	$(UV) sync --extra dev

db-upgrade:
	$(PYTHON) -m alembic upgrade head

dev-gateway:
	$(UV) run uvicorn minutes_gateway.app:create_app --factory --reload --host 0.0.0.0 --port 8000

dev-orchestrator:
	$(UV) run dramatiq minutes_orchestrator.actors -Q orchestrator

dev-inference:
	$(UV) run dramatiq minutes_inference.actors -Q inference

redis:
	$(DOCKER_COMPOSE) up -d redis

format:
	$(RUFF) format src tests scripts

lint:
	$(RUFF) check --fix src tests scripts

test:
	$(PYTEST) -v

check:
	$(RUFF) format --check src tests scripts
	$(RUFF) check src tests scripts
	$(PYTEST) -v

smoke-fake:
	test -n "$(AUDIO)"
	$(PYTHON) scripts/local_run_job.py --fake-inference "$(AUDIO)"

smoke-real:
	test -n "$(AUDIO)"
	$(PYTHON) scripts/local_run_job.py $(if $(STT_URL),--stt-base-url $(STT_URL)) "$(AUDIO)"

docker-up:
	$(DOCKER_COMPOSE) up --build

docker-down:
	$(DOCKER_COMPOSE) down
