# Local Testing

## 快速 smoke
使用 fake inference，验证 `SQLite + ffmpeg + orchestrator + finalize`：

```bash
uv sync --extra dev
uv run python scripts/local_run_job.py --fake-inference /path/to/audio.m4a
```

## 真实 STT 顺序跑
需要先启动一个 OpenAI-compatible STT 服务（如 funasr-server 或 Speaches）：

```bash
# 启动 funasr-server（在 ~/workspaces/tool/funasr-server/）
cd ~/workspaces/tool/funasr-server && make dev

# 然后在 minutes 项目中：
uv run python scripts/local_run_job.py --stt-base-url http://localhost:8101 /path/to/audio.m4a

# 或使用 Speaches（端口 8103）：
uv run python scripts/local_run_job.py --stt-base-url http://localhost:8103 /path/to/audio.m4a
```

## 推荐验证顺序
1. 先跑 `make check`（format + lint + test）
2. 再跑 `uv run alembic upgrade head`
3. 先用 `uv run python scripts/local_run_job.py --fake-inference ...` 跑一段真实音频
4. 最后启动 STT 服务，切到真实转写

## Windows 音频目录

- 用户给出的 `C:\temp\meetings` 在 WSL 中对应 `/mnt/c/temp/meetings`
- 可直接用脚本自动挑选目录里的第一段音频：

```bash
bash scripts/smoke_audio.sh fake /mnt/c/temp/meetings
```
