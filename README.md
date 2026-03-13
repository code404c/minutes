# Minutes Backend

本项目是一个对标飞书妙记的后端骨架，先聚焦"长音频/会议录音 -> 异步转写 -> 结构化结果导出"。

## 架构
- `gateway`：FastAPI 对外入口，负责上传、建任务、查任务、SSE、OpenAI-compatible 薄适配。
- `orchestrator`：CPU 侧任务编排，负责 `ffprobe/ffmpeg`、作业状态机、结果聚合与导出。
- `inference-worker`：通过 HTTP 调用外部 OpenAI-compatible STT 服务（如 funasr-server 或 Speaches）。
- `SQLite`：保存 job 元数据和结果索引。
- `Redis`：承载 Dramatiq 队列与实时事件流。

文字版链路：
`upload -> SQLite create job -> orchestrator prepare -> ffmpeg normalize -> inference-worker POST STT -> orchestrator finalize -> transcript/export`

## 目录
- [`src/minutes_core`](/home/ysnow/workspaces/app/minutes/src/minutes_core)：共享 domain、配置、SQLite、导出、日志、队列封装
- [`src/minutes_gateway`](/home/ysnow/workspaces/app/minutes/src/minutes_gateway)：HTTP API
- [`src/minutes_orchestrator`](/home/ysnow/workspaces/app/minutes/src/minutes_orchestrator)：预处理/收尾任务
- [`src/minutes_inference`](/home/ysnow/workspaces/app/minutes/src/minutes_inference)：STT API 客户端（RemoteSTTEngine）
- [`tests`](/home/ysnow/workspaces/app/minutes/tests)：core、gateway、orchestrator、inference 单元测试
- [`docker-compose.yml`](/home/ysnow/workspaces/app/minutes/docker-compose.yml)：单机容器编排

## 依赖与运行时
- Python 3.12
- FastAPI
- Pydantic v2
- SQLite
- SQLAlchemy 2.x
- Alembic
- Redis
- Dramatiq
- httpx（调用 STT 服务）
- `ffmpeg` / `ffprobe`
- Docker Compose
- Loguru

注意：
- 当前异步任务框架是 `Dramatiq + Redis`
- 不是 `Celery`
- minutes 本身不包含 ASR 模型，需要外部 STT 服务

## 环境变量
默认样例在 [.env.example](/home/ysnow/workspaces/app/minutes/.env.example)。

关键变量：
- `MINUTES_DATABASE_URL`：默认 `sqlite:///data/app/app.db`
- `MINUTES_REDIS_URL`：默认 `redis://redis:6379/0`
- `MINUTES_STORAGE_ROOT`：上传文件、归一化音频、导出文件根目录
- `MINUTES_FAKE_INFERENCE`：设为 `true` 可做本地快速 smoke
- `MINUTES_STT_BASE_URL`：STT 服务地址，默认 `http://localhost:8101`
- `MINUTES_STT_API_KEY`：STT 服务 API key（可选）
- `MINUTES_STT_TIMEOUT_SECONDS`：单次转写超时，默认 600 秒

## 本地运行
安装最小依赖：

```bash
uv sync --extra dev
```

初始化数据库：

```bash
uv run alembic upgrade head
```

只起网关：

```bash
uv run uvicorn minutes_gateway.app:create_app --factory --reload
```

本地串行 smoke（不启容器，不依赖 Redis worker）：

```bash
uv run python scripts/local_run_job.py --fake-inference /path/to/audio.m4a
```

真实 STT smoke（需要 STT 服务运行）：

```bash
# 先启动 STT 服务（如 funasr-server），然后：
uv run python scripts/local_run_job.py --stt-base-url http://localhost:8101 /path/to/audio.m4a
```

## Docker Compose
先准备本地 `.env`。可以直接从 [.env.example](/home/ysnow/workspaces/app/minutes/.env.example) 生成：

```bash
cp .env.example .env
```

启动：

```bash
make docker-up
```

服务：
- `gateway` 暴露 `8000`
- `redis` 暴露 `6379`
- `orchestrator` 与 `inference-worker` 在内部网络消费队列
- inference-worker 通过 `MINUTES_STT_BASE_URL` 指向 STT 服务

## STT 后端
minutes 本身不包含 ASR 模型，而是通过 HTTP 调用外部 OpenAI-compatible STT 服务：

- **funasr-server** (`~/workspaces/tool/funasr-server/`)：FunASR 引擎，默认端口 8101
- **Speaches** (`~/workspaces/tool/speaches/`)：Whisper 引擎，默认端口 8103

通过 `MINUTES_STT_BASE_URL` 环境变量切换后端。

## Claude 交接
如果后续需要让 Claude / Codex 快速接手项目，优先读这份文档：

- [claude-handoff.md](/home/ysnow/workspaces/app/minutes/docs/claude-handoff.md)
- [celery-migration.md](/home/ysnow/workspaces/app/minutes/docs/celery-migration.md)

## 已验证内容
- `make check`：42 个测试通过，覆盖率 80%
- `uv run alembic upgrade head`：迁移可执行
- `docker compose config`：编排文件可解析
- `uv run python scripts/local_run_job.py --fake-inference ...`：本地顺序 smoke 已验证

## 已知限制
- OpenAI-compatible 接口当前只支持同步短音频
- 实时 WebSocket/WebRTC 转写还没进入这一版
