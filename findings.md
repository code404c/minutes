# Findings

- `src/minutes_inference/actors.py` 每次 actor 调用都新建 `InferenceService`，导致 `TTLModelPool` 实际完全失效。
- `src/minutes_inference/model_pool.py` 当前无锁；在多线程 Dramatiq worker 下会出现重复加载和竞争。
- `src/minutes_orchestrator/services.py` 与 `src/minutes_inference/service.py` 缺少状态前置检查；重试或重复投递会导致状态倒退或重复执行。
- `src/minutes_gateway/dependencies.py` 目前用明文 `!=` 比较 API Key，且返回 403；应改为 `hmac.compare_digest` + 401。
- `src/minutes_core/storage.py` 仅在写文件路径上使用上传文件名，存在路径遍历风险；同时 API 层元数据也应改用净化后的文件名。
- `src/minutes_core/events.py` 每次 `publish()` 都新建 Redis client，热路径会造成额外连接开销。
- `src/minutes_core/repositories.py` 当前在 repository 内部直接 `commit()`；若本次重构，需要同步修改所有调用方与测试。
- 仓库当前缺少 `CLAUDE.md`、`.dockerignore`、依赖锁文件和统一自检脚本，与 `../convbox/CLAUDE.md` 的开发约束有明显差距。
- Windows 测试音频路径 `C:\\temp\\meetings` 在当前环境下应按 `/mnt/c/temp/meetings` 尝试访问。
- `/mnt/c/temp/meetings` 实际存在 6 个 `.m4a` 测试音频，可用于后续 smoke。
- `uv sync --extra dev`、`make lint`、`make test`、`make check` 已在当前环境通过，测试总数 31，coverage 76.36%。
- `uv run alembic upgrade head` 已通过，新索引 migration 可执行。
- `docker compose config` 需要本地 `.env`；从 `.env.example` 生成本地 `.env` 后已验证 compose 可解析。
