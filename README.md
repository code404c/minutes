# Minutes Backend

本项目是一个对标飞书妙记的后端骨架，先聚焦“长音频/会议录音 -> 异步转写 -> 结构化结果导出”。

## 架构
- `gateway`：FastAPI 对外入口，负责上传、建任务、查任务、SSE、OpenAI-compatible 薄适配。
- `orchestrator`：CPU 侧任务编排，负责 `ffprobe/ffmpeg`、作业状态机、结果聚合与导出。
- `inference-worker`：GPU 侧推理执行器，负责 `FSMN-VAD -> ASR -> Punc -> Speaker` 链路。
- `SQLite`：保存 job 元数据和结果索引。
- `Redis`：承载 Dramatiq 队列与实时事件流。

文字版链路：
`upload -> SQLite create job -> orchestrator prepare -> ffmpeg normalize -> inference-worker transcribe -> orchestrator finalize -> transcript/export`

## 目录
- [`src/minutes_core`](/home/ysnow/workspaces/app/minutes/src/minutes_core)：共享 domain、配置、SQLite、导出、日志、队列封装
- [`src/minutes_gateway`](/home/ysnow/workspaces/app/minutes/src/minutes_gateway)：HTTP API
- [`src/minutes_orchestrator`](/home/ysnow/workspaces/app/minutes/src/minutes_orchestrator)：预处理/收尾任务
- [`src/minutes_inference`](/home/ysnow/workspaces/app/minutes/src/minutes_inference)：推理服务与模型池
- [`tests`](/home/ysnow/workspaces/app/minutes/tests)：core、gateway、orchestrator smoke tests
- [`docker-compose.yml`](/home/ysnow/workspaces/app/minutes/docker-compose.yml)：单机容器编排

## 依赖与运行时
- Python 3.12
- SQLite
- Redis
- `ffmpeg` / `ffprobe`
- 可选 GPU 推理依赖：`funasr`、`modelscope`、`torch`

## 环境变量
默认样例在 [.env.example](/home/ysnow/workspaces/app/minutes/.env.example)。

关键变量：
- `MINUTES_DATABASE_URL`：默认 `sqlite:///data/app/app.db`
- `MINUTES_REDIS_URL`：默认 `redis://redis:6379/0`
- `MINUTES_STORAGE_ROOT`：上传文件、归一化音频、导出文件根目录
- `MINUTES_FAKE_INFERENCE`：设为 `true` 可做本地快速 smoke
- `MINUTES_INFERENCE_DEVICE`：默认 `cuda:0`

## 本地运行
安装最小依赖：

```bash
python3 -m pip install -e '.[dev]'
```

初始化数据库：

```bash
python3 -m alembic upgrade head
```

只起网关：

```bash
uvicorn minutes_gateway.app:create_app --factory --reload
```

本地串行 smoke（不启容器，不依赖 Redis worker）：

```bash
python3 scripts/local_run_job.py --fake-inference /path/to/audio.m4a
```

真实模型本地顺序跑：

```bash
python3 scripts/local_run_job.py /path/to/audio.m4a
```

## Docker Compose
先准备 `.env`，仓库里已经放了一份默认 [.env](/home/ysnow/workspaces/app/minutes/.env)。

启动：

```bash
docker compose up --build
```

服务：
- `gateway` 暴露 `8000`
- `redis` 暴露 `6379`
- `orchestrator` 与 `inference-worker` 在内部网络消费队列

## 已验证内容
- `pytest -q`：当前 `14 passed`
- `python3 -m alembic upgrade head`：迁移可执行
- `docker compose config`：编排文件可解析
- `python3 scripts/local_run_job.py --fake-inference ...`：本地顺序 smoke 已验证

## 真实模型测试提示
- 本机 `modelscope` 缓存默认假设在 `~/.cache/modelscope`
- `cn_meeting` 使用 `Paraformer-large + FSMN-VAD + CT-Punc`
- `multilingual_rich` 使用 `SenseVoiceSmall`
- 真模型链路仍建议先用一段较短音频验证依赖和显存，再跑长会录音

## 已知限制
- `CAM++` 当前只作为段级 speaker embedding 使用，不是完整 overlap-aware diarization
- OpenAI-compatible 接口当前只支持同步短音频
- 实时 WebSocket/WebRTC 转写还没进入这一版
- 真实 FunASR GPU 端到端链路代码已接好，但仍需要实机再做一次完整长音频验证

