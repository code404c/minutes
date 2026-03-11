# Minutes 项目全面 Code Review

> 审查日期: 2026-03-12
> 审查工具: Claude Code (5 并行 agent)
> 代码状态: commit f7eaa86, 17 测试全部通过, 覆盖率 75%

## 项目概况

会议录音转文字后端，架构：FastAPI Gateway + Dramatiq Orchestrator + FunASR Inference Worker，SQLite + Redis，3 个 Docker 容器。Codex 生成的脚手架代码。

---

## 🔴 严重问题（13 个）

### 架构 & 运行时

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | **模型池完全失效** — 每次 actor 调用都新建 `InferenceService`，`TTLModelPool` 永远 cache miss，每次推理重新加载模型（30-60s） | `src/minutes_inference/actors.py:14` | **最严重的性能问题** |
| 2 | **`TTLModelPool` 非线程安全** — 多线程 worker 下可能重复加载模型导致 GPU OOM | `src/minutes_inference/model_pool.py:16-33` | 运行时崩溃 |
| 3 | **Actor 无重试/超时配置** — Dramatiq 默认无限重试，挂住的推理永远阻塞 worker | `src/minutes_orchestrator/actors.py`, `src/minutes_inference/actors.py` | 资源耗尽 |
| 4 | **全异常捕获阻止 Dramatiq 重试** — 临时错误（CUDA OOM）直接标 FAILED | `src/minutes_inference/service.py:56-65`, `src/minutes_orchestrator/services.py:90` | 任务丢失 |
| 5 | **缺乏幂等性保护** — 重试可能导致状态倒退（TRANSCRIBING → PREPROCESSING） | `src/minutes_orchestrator/services.py:31-75` | Pipeline 状态混乱 |
| 6 | **无分布式锁** — 同一 job 可能被多 worker 并发处理 | 全局 | 文件损坏 |
| 7 | **SQLite 多容器共享** — 3 个容器通过 volume 共享同一 SQLite 文件 | `docker-compose.yml:22,46,64` | `database is locked` |

### 安全

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 8 | **API Key 时序攻击** — `!=` 比较可被逐字节猜测，应使用 `hmac.compare_digest` | `src/minutes_gateway/dependencies.py:19-30` | 密钥泄露 |
| 9 | **文件名路径遍历** — `upload.filename` 未过滤，`../../etc/passwd` 可写任意路径，应使用 `Path(filename).name` 过滤 | `src/minutes_core/storage.py:28` | 任意文件写入 |
| 10 | **API Key 验证返回 403 而非 401** — 身份未验证应返回 401 | `src/minutes_gateway/dependencies.py:28` | 不符合 HTTP 规范 |

### 数据层

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 11 | **Migration 缺少索引** — `status`、`created_at` 无索引 | `alembic/versions/20260311_0001_init_jobs.py` | 查询性能 |
| 12 | **Repository 内部 commit** — 破坏事务组合能力，应将 commit 移到调用方 | `src/minutes_core/repositories.py:36,79,93` | 数据不一致 |
| 13 | **`EventBus.publish` 每次新建 Redis 连接** — 应复用连接或使用连接池 | `src/minutes_core/events.py:21-26` | 连接风暴 |

---

## 🟡 建议改进

### API 层

- `src/minutes_gateway/routers/openai.py:30-52`: `_await_job_completion` 轮询数据库（每 200ms），应改用 EventBus 事件驱动
- `src/minutes_gateway/routers/jobs.py:46-72`: 缺少文件类型白名单（`ALLOWED_CONTENT_TYPES`）和文件大小限制
- `src/minutes_gateway/app.py`: 缺少 CORS 配置和 Rate Limiting
- `src/minutes_gateway/routers/jobs.py:96`: `format` 参数未用 `Literal`/`Enum` 约束
- `src/minutes_gateway/routers/openai.py:86` vs `jobs.py:27-31`: `hotwords` 解析逻辑不一致，应复用 `_parse_hotwords`
- `src/minutes_gateway/app.py`: 缺少全局异常处理器（`@app.exception_handler(Exception)`），500 可能泄露内部细节
- `src/minutes_gateway/routers/openai.py:93-101`: OpenAI 兼容 API 错误格式不符合标准（`{"error": {...}}` vs `{"detail": ...}`），`verbose_json` 返回结构与 OpenAI 规范不兼容
- `src/minutes_gateway/dependencies.py:46-47`: `get_job_repository` 已定义但未使用

### 推理 & 编排

- `src/minutes_inference/model_pool.py:25-27`: 模型过期后未显式释放 GPU 内存，应调用 `torch.cuda.empty_cache()`
- 全局: 无死信队列（DLQ）配置，失败任务静默丢弃
- `src/minutes_inference/engines/funasr_engine.py:31`: `batch_size_s=60` 硬编码，无法适配不同 GPU 显存
- `src/minutes_inference/service.py:47-50`: 引擎选择是硬编码 if/else，扩展需改源码，建议用注册机制
- `src/minutes_inference/engines/base.py`: `InferenceEngine` Protocol 定义了但未被类型引用
- `src/minutes_inference/engines/`: 目录缺少 `__init__.py`

### 数据 & 配置

- `src/minutes_core/repositories.py:70-76`: `update_job` 无法将字段重置为 None，需 sentinel 模式（`_UNSET = object()`）
- `src/minutes_core/config.py:21`: `database_url` 应使用 `SecretStr`（迁移 PostgreSQL 后会泄露凭据）
- `src/minutes_core/config.py:23`: `storage_root` 默认相对路径 `Path("data/app")`，启动目录不同会写错位置
- `src/minutes_core/models.py:34`: `sync_mode` 用 Integer 而非 Boolean
- `src/minutes_core/schemas.py:39-40`: `source_filename` 缺少长度限制和危险字符过滤
- `src/minutes_core/logging.py:10-11`: ContextVar 未被 loguru patcher 自动读取，直接 `logger.info()` 不带 context
- `src/minutes_core/media.py:32,56`: `subprocess.run` 缺少 `timeout` 参数
- `src/minutes_core/repositories.py:60`: `KeyError(job_id)` 不够语义化，建议自定义 `JobNotFoundError`

### 基础设施

- 缺少 `.dockerignore`（`.git/`、`.env`、`data/` 进入 build context）
- 缺少依赖锁文件（`pip-compile` 或 `uv lock`），每次构建可能安装不同版本
- 三个 Dockerfile 未创建非 root 用户
- Dockerfile 无多阶段构建、先 COPY src 后 pip install 导致 layer 缓存失效
- `docker-compose.yml`: 缺少 `restart: unless-stopped`、`mem_limit`、orchestrator/inference 健康检查
- `docker-compose.yml:73`: `gpus: all` 应改用标准 `deploy.resources.reservations.devices` 语法
- `.env` 与 `.env.example` 不一致（容器路径 vs 相对路径）
- `alembic.ini:3`: 硬编码 `sqlite:///data/app/app.db`，应改为空字符串
- `pyproject.toml:9`: `readme` 字段指向实现计划文档而非 README.md

### 测试

- `src/minutes_inference/engines/funasr_engine.py`: `_build_segments/_build_speakers` 覆盖率 0%（纯数据转换逻辑，测试 ROI 最高）
- `src/minutes_inference/model_pool.py`: `TTLModelPool` 无单元测试
- `src/minutes_gateway/dependencies.py:19-30`: `verify_api_key` 安全路径无测试
- `tests/gateway/test_jobs_api.py`: 缺少 404/409 错误路径测试
- `tests/gateway/test_openai_api.py`: 缺少成功路径测试（只测了三个异常场景）
- `tests/conftest.py` vs `tests/gateway/conftest.py`: 存在重复 Fake 实现（`FakeQueueDispatcher` / `FakeDispatcher`）
- `pyproject.toml`: 缺少 `[tool.coverage.run]` 配置和 `fail_under` 门槛

---

## 🟢 亮点

- **架构分层清晰** — core/gateway/orchestrator/inference 四包零循环依赖
- **依赖注入优秀** — Protocol + lazy import + factory 注入，可测试性极好
- **队列分离** — orchestrator/inference 独立 queue，可独立扩缩容
- **SQLite WAL + busy_timeout** — 并发读写最佳实践 (`db.py:27-34`)
- **测试 harness** — `GatewayHarness` + `FakeDispatcher` 的回调机制精良
- **Shell 脚本** — `set -euo pipefail` + `exec`
- **文档** — `claude-handoff.md` 和 `celery-migration.md` 质量很高
- **SecretStr** — API key 使用 `SecretStr` 防止日志泄露 (`config.py:24`)
- **结构化日志** — loguru JSON + ContextVar 方案 (`logging.py`)

---

## 修复优先级

### P0 — 上线前必须修复

1. `InferenceService` 改为模块级单例，使模型池真正生效
2. `TTLModelPool` 加 `threading.Lock`
3. Actor 配置 `max_retries=2, time_limit=1800_000, max_age=3600_000`
4. `verify_api_key` 改用 `hmac.compare_digest`，状态码改为 401
5. `upload.filename` 路径安全过滤：`Path(filename).name`
6. Service 方法入口加状态前置检查（幂等性保护）

### P1 — 上线后短期修复

7. 创建 `.dockerignore`
8. 生成依赖锁文件（`uv lock` 或 `pip-compile`）
9. 区分可重试/不可重试异常（临时错误 re-raise 让 Dramatiq 重试）
10. `_await_job_completion` 改为基于 EventBus 的事件驱动等待
11. `EventBus` 复用 Redis 连接（`__init__` 中创建，复用）
12. 添加数据库索引（`status`, `created_at`）
13. Repository 事务管理重构（commit 移到调用方，Repository 只 flush）

### P2 — 持续改进

14. 迁移 PostgreSQL 替代 SQLite 多容器共享
15. 补充核心测试（FunASR 转换逻辑、模型池、安全路径、错误路径）
16. Dockerfile 优化（非 root 用户、多阶段构建、layer 缓存）
17. 死信队列 + Redis 分布式锁
18. OpenAI 兼容 API 规范完善（错误格式、verbose_json）
19. 全局异常处理器 + CORS + Rate Limiting
20. `update_job` sentinel 模式、`subprocess` 超时、配置字段修正

---

## 修复参考

### #1 InferenceService 单例化

```python
# src/minutes_inference/actors.py
_inference_service: InferenceService | None = None

def _get_inference_service() -> InferenceService:
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService(settings=settings)
    return _inference_service

@dramatiq.actor(queue_name="inference", max_retries=2, time_limit=1800_000)
def transcribe_job_actor(job_id: str) -> None:
    _get_inference_service().transcribe_job(job_id)
```

### #2 TTLModelPool 线程安全

```python
import threading

class TTLModelPool(Generic[T]):
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, PoolEntry[T]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self.ttl_seconds >= 0 and time.monotonic() - entry.last_used > self.ttl_seconds:
                self._entries.pop(key, None)
                return None
            entry.last_used = time.monotonic()
            return entry.value

    def put(self, key: str, value: T) -> None:
        with self._lock:
            self._entries[key] = PoolEntry(value=value, last_used=time.monotonic())
```

### #4 API Key 安全比较

```python
import hmac

def verify_api_key(request: Request) -> None:
    expected = get_settings().api_key
    if expected is None:
        return
    header = request.headers.get("Authorization", "")
    expected_str = f"Bearer {expected.get_secret_value()}"
    if not hmac.compare_digest(header, expected_str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
```

### #5 文件名安全过滤

```python
# src/minutes_core/storage.py
filename = Path(upload.filename or "upload.bin").name  # 只取文件名，剥离路径
```

### #6 幂等性保护

```python
# src/minutes_orchestrator/services.py
def prepare_job(self, job_id: str) -> None:
    with self.session_factory() as session:
        repository = JobRepository(session)
        detail = repository.get_job(job_id)
        if detail is None:
            raise KeyError(job_id)
        if detail.status != JobStatus.QUEUED:
            logger.warning("Job %s already in %s, skipping prepare", job_id, detail.status)
            return
        # ... 继续处理
```

---

## 与 convbox 项目规范对齐

minutes 是同团队项目，应参考 `workspaces/app/convbox` 的成熟规范。以下是需要对齐的关键项：

### 工具链对齐

| 项目 | convbox（标准） | minutes（当前） | 需要做的 |
|------|----------------|----------------|---------|
| 包管理器 | **uv** + `uv.lock` | pip（无锁文件） | 迁移到 uv，生成 `uv.lock` |
| Linter/Formatter | **ruff** | 无 | 添加 ruff 配置到 `pyproject.toml`，添加 `make lint` |
| 测试执行 | `uv run pytest` | `python -m pytest` | 统一为 `uv run pytest` |
| Makefile | 完整的 `make help/dev/test/lint/docker-build` | 无 | 创建 Makefile |

### 需要创建的 Makefile

参考 convbox，minutes 的 Makefile 至少应包含：

```makefile
UV := uv
PYTHON := $(UV) run python
PYTEST := $(UV) run pytest
DOCKER_COMPOSE := docker compose

.PHONY: help install dev dev-gateway dev-orchestrator dev-inference test lint format

help:
	@echo "开发:"
	@echo "  make install          - 同步依赖 (uv sync)"
	@echo "  make dev-gateway      - 启动 Gateway (热重载)"
	@echo "  make dev-orchestrator - 启动 Orchestrator worker"
	@echo "  make dev-inference    - 启动 Inference worker"
	@echo "  make redis            - 启动 Redis"
	@echo ""
	@echo "代码质量:"
	@echo "  make lint             - 格式化 + 检查 (ruff)"
	@echo "  make test             - 运行测试"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up        - docker compose up"
	@echo "  make docker-down      - docker compose down"

install:
	$(UV) sync

dev-gateway:
	$(UV) run uvicorn minutes_gateway.app:create_app --factory --reload --host 0.0.0.0 --port 8000

dev-orchestrator:
	$(UV) run dramatiq minutes_orchestrator.actors -Q orchestrator

dev-inference:
	$(UV) run dramatiq minutes_inference.actors -Q inference

redis:
	$(DOCKER_COMPOSE) up -d redis

format:
	$(UV) run ruff format src tests

check:
	$(UV) run ruff check src tests

lint: format
	$(UV) run ruff check --fix src tests

test:
	$(PYTEST) -v

docker-up:
	$(DOCKER_COMPOSE) up -d

docker-down:
	$(DOCKER_COMPOSE) down
```

### 需要创建的 CLAUDE.md

minutes 项目缺少 `CLAUDE.md`，公司开发机的 Claude Code 需要它来理解项目。参考 convbox 格式，至少包含：

```markdown
# minutes 项目指南

会议录音转文字后端服务，提供 OpenAI 兼容 API。

## Call Flow Cheat Sheet

- Gateway entry: `src/minutes_gateway/app.py` -> `routers/jobs.py`, `routers/openai.py`
- Orchestrator: `src/minutes_orchestrator/actors.py` -> `services.py`
- Inference: `src/minutes_inference/actors.py` -> `service.py` -> `engines/`
- Core: `src/minutes_core/` (models, schemas, repositories, config, events, queue)
- Docker: `docker-compose.yml` + `docker/*.Dockerfile`

## 工具链（禁止替换）

| 层级 | 包管理器 | 测试框架 | Linter/Formatter | 配置文件 |
|------|---------|---------|-----------------|---------|
| 后端 (Python) | **uv** | **pytest** | **ruff** | `pyproject.toml` + `uv.lock` |

常用命令：
- 安装依赖: `make install`
- 测试: `make test`
- 格式化+检查: `make lint`

## 架构

Pipeline: Gateway -> prepare_job (orchestrator queue) -> transcribe_job (inference queue) -> finalize_job (orchestrator queue)

- Gateway: FastAPI，接收上传，提供 REST + OpenAI 兼容 API + SSE
- Orchestrator: Dramatiq actor，音频预处理 (ffmpeg) + 结果整理
- Inference: Dramatiq actor，FunASR 语音识别
- Core: 共享模块（models, schemas, config, events, queue）

## 代码规范

- 注释、文档字符串: 简体中文
- 日志、代码内文本: 英文
- 所有生产镜像必须带版本号，严禁 latest

## 开发服务管理

| 服务 | 启动 | 何时需要 |
|------|------|---------|
| Redis | `make redis` | 消息队列 |
| Gateway | `make dev-gateway` | API 开发 |
| Orchestrator | `make dev-orchestrator` | 音频预处理调试 |
| Inference | `make dev-inference` | 推理调试（需 GPU） |
```

### pyproject.toml 需要添加的配置

```toml
[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.ruff.format]
quote-style = "double"
```

### 其他对齐项

- `pyproject.toml` 的 `readme` 字段改为 `"README.md"`（当前指向 plan 文档）
- 代码审查文档应放 `docs/reviews/` 目录（convbox 惯例）
- 迁移到 uv 后在 Dockerfile 中也用 `uv pip install` 替代 `pip install`
