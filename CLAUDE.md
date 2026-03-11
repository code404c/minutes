# minutes 项目指南

会议录音转文字后端服务，提供异步 Job API、SSE 事件流和 OpenAI 兼容同步接口。

## Call Flow Cheat Sheet

- Gateway entry: `src/minutes_gateway/app.py`
- Job API: `src/minutes_gateway/routers/jobs.py`
- OpenAI-compatible API: `src/minutes_gateway/routers/openai.py`
- Queue entry: `src/minutes_orchestrator/actors.py` -> `src/minutes_orchestrator/services.py`
- Inference entry: `src/minutes_inference/actors.py` -> `src/minutes_inference/service.py` -> `src/minutes_inference/engines/`
- Retry exhausted: `src/minutes_orchestrator/actors.py::handle_orchestrator_retry_exhausted`, `src/minutes_inference/actors.py::handle_inference_retry_exhausted`
- Shared core: `src/minutes_core/`
- Local smoke: `scripts/local_run_job.py`
- Docker entry: `docker-compose.yml` + `docker/*.Dockerfile`

## 工具链（禁止替换）

| 层级 | 包管理器 | 测试框架 | Linter/Formatter | 配置文件 |
|------|---------|---------|-----------------|---------|
| 后端 (Python) | **uv** | **pytest** | **ruff** | `pyproject.toml` + `uv.lock` |

常用命令：
- 安装依赖: `make install`
- 数据库迁移: `make db-upgrade`
- 格式化: `make format`
- 检查: `make lint`
- 全量检查: `make check`
- 测试: `make test`
- 下载模型: `make download-models`

## 架构

Pipeline:
`upload -> create job -> prepare_job -> transcribe_job -> finalize_job -> transcript/export`

- Gateway: FastAPI，对外提供 REST、SSE 和 OpenAI 兼容接口
- Orchestrator: Dramatiq worker，负责 `ffprobe/ffmpeg`、状态机和收尾
- Inference: Dramatiq worker，负责 Fake/FunASR 推理
- Core: 配置、数据库、仓储、事件总线、导出与存储

## 开发服务管理

需要服务时，先检查再启动，尽量不要要求用户手工开多个终端。

| 服务 | 检查 | 启动 | 何时需要 |
|------|------|------|---------|
| Redis | `redis-cli ping` | `make redis` | 队列与事件流 |
| Gateway | `curl -sf http://127.0.0.1:8000/health` | `make dev-gateway` | API 开发 |
| Orchestrator | `pgrep -f 'dramatiq minutes_orchestrator.actors'` | `make dev-orchestrator` | 预处理调试 |
| Inference | `pgrep -f 'dramatiq minutes_inference.actors'` | `make dev-inference` | 推理调试 |

轻量模式：
- 仅跑单机 smoke: 直接用 `scripts/local_run_job.py`
- 调 API 但不测异步 worker: 启动 Gateway 即可
- 调异步链路: Gateway + Redis + 对应 worker

## 模型与音频 smoke

- 默认模型预热脚本: `scripts/download_models.py`
- Windows 测试目录 `C:\temp\meetings` 在 WSL 中对应 `/mnt/c/temp/meetings`
- Fake smoke:
  - `make smoke-fake AUDIO=/mnt/c/temp/meetings/demo.wav`
- Real smoke:
  - 先 `make download-models`
  - 再 `make smoke-real AUDIO=/mnt/c/temp/meetings/demo.wav`

## 代码规范

- 注释、文档字符串: 简体中文
- 日志、代码内文本: 英文
- 显式优于隐式，关键调用优先显式参数
- 不要在 repository 内部隐式提交事务；由调用方决定 `commit/rollback`
- 新增路由、服务入口、状态流转或模型配置时，必须同步更新本文件和对应文档

## 提交前自检（必须执行）

- 每次准备提交前，先运行 `make check`
- 然后启动一个 subagent 对本次变更做自检，至少覆盖：
  1. `CLAUDE.md` 是否需要同步
  2. 新增/修改的状态机、actor、router、脚本是否有测试覆盖
  3. 新增日志是否为英文，新增用户可见文本是否为简体中文
  4. 文档命令是否仍与仓库实际工具链一致
  5. 是否引入未锁定依赖或未记录的运行前提
- subagent 发现问题时，先修复，再提交

## 文档规范

- 计划文档放 `docs/plans/`
- 评审文档放 `docs/reviews/`
- 指南文档放 `docs/guides/`
- 本地测试说明与模型准备步骤变更时，务必同步更新 `README.md` 和 `docs/local-testing.md`
