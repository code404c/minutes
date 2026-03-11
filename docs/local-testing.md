# Local Testing

## 快速 smoke
使用 fake inference，验证 `SQLite + ffmpeg + orchestrator + finalize`：

```bash
uv sync --extra dev
uv run python scripts/local_run_job.py --fake-inference /path/to/audio.m4a
```

## 真实模型顺序跑
确保本机已经安装 `funasr`、`modelscope`、`torch`，并先下载默认模型：

```bash
uv sync --extra dev --extra inference
uv run python scripts/download_models.py
uv run python scripts/local_run_job.py /path/to/audio.m4a
```

## 推荐验证顺序
1. 先跑 `uv run pytest -q`
2. 再跑 `uv run alembic upgrade head`
3. 先用 `uv run python scripts/local_run_job.py --fake-inference ...` 跑一段真实音频
4. 最后再切到真实模型

## Windows 音频目录

- 用户给出的 `C:\temp\meetings` 在 WSL 中对应 `/mnt/c/temp/meetings`
- 可直接用脚本自动挑选目录里的第一段音频：

```bash
bash scripts/smoke_audio.sh fake /mnt/c/temp/meetings
```
