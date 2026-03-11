# Local Testing

## 快速 smoke
使用 fake inference，验证 `SQLite + ffmpeg + orchestrator + finalize`：

```bash
python3 scripts/local_run_job.py --fake-inference /path/to/audio.m4a
```

## 真实模型顺序跑
确保本机已经安装 `funasr`、`modelscope`、`torch`，并且 `~/.cache/modelscope` 下已有模型：

```bash
python3 -m pip install -e '.[dev,inference]'
python3 scripts/local_run_job.py /path/to/audio.m4a
```

## 推荐验证顺序
1. 先跑 `pytest -q`
2. 再跑 `python3 -m alembic upgrade head`
3. 先用 `--fake-inference` 跑一段真实音频
4. 最后再切到真实模型

