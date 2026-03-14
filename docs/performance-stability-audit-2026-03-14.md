# 性能与稳定性全面检查（2026-03-14）

## 目标与范围
本次检查覆盖：
- 代码质量（格式与静态检查）
- 可执行性（语法编译）
- 测试可运行性与环境阻塞点
- 关键链路的性能/稳定性代码审查（gateway/orchestrator/inference/event bus）
- 文档一致性与后续改进建议

## 已执行检查

### 1) 代码质量
- `uv run ruff format --check src tests scripts`：通过
- `uv run ruff check src tests scripts`：通过

修复项：
- 修复 `tests/gateway/conftest.py` 中重复命名导入引发的 `F811`，避免 `make check` 在 lint 阶段直接失败。

### 2) 语法与可导入性（无需第三方运行时）
- `python -m compileall src tests scripts`：通过

结论：所有 `src/tests/scripts` 下 Python 文件语法层面可编译。

### 3) 测试运行与环境可用性
- `make check`：失败（环境依赖未完成）
  - 失败原因：`ModuleNotFoundError: No module named 'pydantic'`
- `uv sync --extra dev`：失败（网络拉取依赖受限）
  - 失败原因：下载 `packaging==26.0` 时连接隧道错误

结论：当前环境不满足完整 pytest 执行条件，属于“外部依赖安装受阻”而不是项目测试本身逻辑失败。

### 4) 运行环境工具可用性
- `docker compose config`：失败（环境缺少 docker 命令）

结论：本次无法完成容器维度 smoke 与 compose 解析复验。

## 性能与稳定性审查结论（代码层）

### A. 事件订阅轮询策略存在固定 sleep，吞吐/时延有优化空间
- `EventBus.subscribe()` 每轮 `get_message(timeout=1.0)` 后固定 `sleep(0.1)`；在高频事件下会增加额外处理延迟，在低频时会增加空轮询周期。
- 建议：将 sleep 退化为“仅在无消息时 sleep”，或改为更事件驱动的读取策略。

### B. 推理与编排主链路具备幂等/短路保护，稳定性基线较好
- inference 在任务不存在、状态不应执行、缺少归一化路径、已有产物时都有早返回。
- orchestrator finalize 对“结果已存在”“输入缺失”“结果 JSON 校验失败”都有显式分支。
- 这对重试场景下避免重复处理与状态回退是正向设计。

### C. 推理引擎实例创建策略可再评估
- `InferenceService.transcribe_job()` 中每次任务都会构建 `FakeInferenceEngine` 或 `RemoteSTTEngine`。
- 对远程 HTTP 引擎而言，若后续接入连接池复用或会话级资源，建议评估将引擎提升为服务级复用对象，减少对象构建开销。

## 文档建议
- 建议把本检查文档纳入 `docs/` 的定期审查记录，并在 README 的“已验证内容”中补充“依赖安装失败时的最小静态检查清单”，便于 CI/本地快速判定问题归因。

## 下一步建议（优先级）
1. **P0**：在可联网/可安装依赖环境中重新执行 `uv sync --extra dev && make check`，恢复完整测试闭环。
2. **P1**：优化 `EventBus.subscribe()` 的无消息等待策略，减少固定 sleep 带来的时延和空转。
3. **P1**：评估 inference 引擎实例复用策略，在高并发任务下降低重复构建成本。
4. **P2**：在 CI 增加“环境自检提示”（依赖安装、docker 可用性），把环境问题与代码问题区分展示。
