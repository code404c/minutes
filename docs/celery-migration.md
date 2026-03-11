# Migrating From Dramatiq To Celery

这份文档说明当前 `Minutes Backend` 如何从 `Dramatiq + Redis` 迁移到 `Celery + Redis`。

目标不是立刻改代码，而是把迁移路径写成“后续 Claude / 人类工程师可以直接执行”的说明书。

## 1. 当前现状

当前项目的异步任务栈是：

- `Redis`
  - 作为 queue broker
  - 作为 SSE 事件通道
- `Dramatiq`
  - 作为后台任务执行框架
- 当前任务链路
  - `prepare_job`
  - `transcribe_job`
  - `finalize_job`

当前相关代码主要在：

- [`queue.py`](/home/ysnow/workspaces/app/minutes/src/minutes_core/queue.py)
- [`actors.py`](/home/ysnow/workspaces/app/minutes/src/minutes_orchestrator/actors.py)
- [`actors.py`](/home/ysnow/workspaces/app/minutes/src/minutes_inference/actors.py)
- [`services.py`](/home/ysnow/workspaces/app/minutes/src/minutes_orchestrator/services.py)
- [`service.py`](/home/ysnow/workspaces/app/minutes/src/minutes_inference/service.py)
- [`docker-compose.yml`](/home/ysnow/workspaces/app/minutes/docker-compose.yml)
- [`run-orchestrator.sh`](/home/ysnow/workspaces/app/minutes/scripts/run-orchestrator.sh)
- [`run-inference-worker.sh`](/home/ysnow/workspaces/app/minutes/scripts/run-inference-worker.sh)

## 2. 为什么现在迁移是可行的

当前仓库在任务系统上做了一层很薄的抽象，所以切到 `Celery` 不算推倒重来。

有利因素：

- 业务逻辑已经沉淀在 service 层
  - `OrchestratorService`
  - `InferenceService`
- actor 文件只是在调用 service
- `QueueDispatcher` 已经把“谁来发任务”与“任务做什么”分开了
- 任务状态持久化在 `SQLite`
  - 不依赖 Dramatiq 自己的状态存储

这意味着迁移时真正要换的是：

- 任务定义方式
- 任务发送方式
- worker 启动命令
- 依赖和容器镜像

而不是：

- API 协议
- 数据库模型
- Transcript 数据结构
- ffmpeg / FunASR 主流程

## 3. 迁移范围

### 必改

- 移除 `Dramatiq` 依赖
- 新增 `Celery` 依赖
- 新建 Celery app
- 把 `@dramatiq.actor` 改成 `@celery_app.task`
- 把 `prepare_job_actor.send(...)` 改成 `prepare_job_task.delay(...)`
- 改 worker 启动脚本
- 改 compose 服务命令

### 可以保持不变

- FastAPI 层
- `JobRepository`
- `SQLite`
- `EventBus`
- `ffmpeg/ffprobe`
- `FunASREngine`
- `local_run_job.py`

### 建议顺手重构

- 把“队列调度”和“任务函数 import 路径”再解耦一点
- 给任务名统一加 namespace，避免后续扩展时碰撞
- 把 worker 配置集中到单独模块，别散在 actor 文件里

## 4. 技术映射

### 当前 Dramatiq 写法

```python
@dramatiq.actor(queue_name="orchestrator")
def prepare_job_actor(job_id: str) -> None:
    OrchestratorService(settings=settings).prepare_job(job_id)
```

```python
prepare_job_actor.send(job_id)
```

### 目标 Celery 写法

```python
@celery_app.task(name="minutes.orchestrator.prepare_job", queue="orchestrator")
def prepare_job_task(job_id: str) -> None:
    OrchestratorService(settings=settings).prepare_job(job_id)
```

```python
prepare_job_task.delay(job_id)
```

## 5. 推荐迁移步骤

按这个顺序迁移最稳，不容易把网关和 worker 同时打坏。

### Step 1: 新建 Celery app，不动现有 Dramatiq

先新增一个模块，例如：

- `src/minutes_core/celery_app.py`

职责：

- 创建 `Celery("minutes")`
- 设置 `broker_url`
- 可选设置 `result_backend`
- 配置 task routes

建议配置：

- broker：继续用 `Redis`
- result backend：第一阶段可以不强依赖
  - 因为当前结果主要落 `SQLite`
- task routes：
  - `minutes.orchestrator.* -> orchestrator`
  - `minutes.inference.* -> inference`

### Step 2: 并行保留 actor，新增 Celery task

不要一上来直接删 Dramatiq。

更稳的做法是：

- 新增 Celery task 文件
- 让它们内部调用同一个 service 层
- 先让 Celery worker 能独立跑起来

推荐新增：

- `src/minutes_orchestrator/celery_tasks.py`
- `src/minutes_inference/celery_tasks.py`

### Step 3: 新增 Celery 版 dispatcher

当前 dispatcher 在：

- [`queue.py`](/home/ysnow/workspaces/app/minutes/src/minutes_core/queue.py)

建议做法：

- 保留现有 `QueueDispatcher` protocol
- 新增 `CeleryQueueDispatcher`
- 暂时不要删除 `DramatiqQueueDispatcher`

这样可以让切换变成配置层面的，而不是一次性重写。

建议增加：

- `MINUTES_TASK_BACKEND=dramatiq|celery`

然后在 app 启动时按配置注入不同 dispatcher。

### Step 4: 切换 worker 启动脚本

当前脚本：

- [`run-orchestrator.sh`](/home/ysnow/workspaces/app/minutes/scripts/run-orchestrator.sh)
- [`run-inference-worker.sh`](/home/ysnow/workspaces/app/minutes/scripts/run-inference-worker.sh)

当前命令类似：

```bash
dramatiq minutes_orchestrator.actors --processes 1 --threads 1
```

迁移后建议变成：

```bash
celery -A minutes_orchestrator.celery_tasks worker -Q orchestrator --loglevel=INFO
```

```bash
celery -A minutes_inference.celery_tasks worker -Q inference --loglevel=INFO
```

更专业一点的做法是：

- 不拆两个 Celery app
- 统一用一个 `minutes_core.celery_app:celery_app`
- worker 仅通过队列名过滤消费

例如：

```bash
celery -A minutes_core.celery_app:celery_app worker -Q orchestrator --loglevel=INFO
celery -A minutes_core.celery_app:celery_app worker -Q inference --loglevel=INFO
```

这比“每个服务一个 app”更好维护。

### Step 5: compose 切 Celery worker

改 [`docker-compose.yml`](/home/ysnow/workspaces/app/minutes/docker-compose.yml)：

- worker 镜像可以先不动
- command 改成 Celery worker 启动命令
- Redis 继续复用

### Step 6: 最后删除 Dramatiq

只有在下面这些都通过后，才删 Dramatiq：

- API smoke tests 通过
- orchestrator 链路 smoke tests 通过
- fake inference 本地顺序跑通过
- Celery worker 实际能消费任务

然后再删：

- `dramatiq` 依赖
- `configure_broker`
- `DramatiqQueueDispatcher`
- 旧 actor 文件或旧命令

## 6. 建议的新文件结构

迁移到 Celery 后，建议结构如下：

```text
src/
├── minutes_core/
│   ├── celery_app.py
│   └── queue.py
├── minutes_orchestrator/
│   ├── services.py
│   └── celery_tasks.py
└── minutes_inference/
    ├── service.py
    └── celery_tasks.py
```

## 7. 代码级修改清单

### A. `pyproject.toml`

替换依赖：

- 删除 `dramatiq[redis]`
- 新增 `celery[redis]`

### B. `src/minutes_core/queue.py`

建议修改为：

- 保留 `QueueDispatcher` protocol
- 新增 `CeleryQueueDispatcher`
- 增加 `build_queue_dispatcher(settings)` 工厂函数

原因：

- 当前网关不应该知道底层到底是 Dramatiq 还是 Celery
- 用工厂函数可以降低后续再次迁移的成本

### C. `src/minutes_gateway/app.py`

当前默认注入的是 `DramatiqQueueDispatcher`。

迁移后应改成：

- 按配置选择 dispatcher
- 默认值可以切成 celery

### D. `src/minutes_orchestrator/actors.py`

这个文件最终会被 `celery_tasks.py` 替代。

### E. `src/minutes_inference/actors.py`

同上。

### F. `scripts/run-orchestrator.sh`

从 Dramatiq CLI 改成 Celery CLI。

### G. `scripts/run-inference-worker.sh`

同上。

### H. `docker-compose.yml`

改 command，必要时增加：

- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

不过更推荐继续统一走已有环境变量：

- `MINUTES_REDIS_URL`

然后在 Celery app 内部做映射。

## 8. 风险点

### 1. Celery 默认心智模型比 Dramatiq 重

风险：

- 接手的人容易把任务状态管理“做两套”
  - 一套在 Celery backend
  - 一套在 SQLite

建议：

- 当前版本继续以 `SQLite` 为唯一业务状态来源
- Celery 只负责执行，不负责业务结果真相

### 2. 不要把 task result backend 绑定成核心业务依赖

如果你开始依赖 `AsyncResult` 查 transcript 状态，就会和当前 `JobRepository` 设计冲突。

建议：

- API 查询仍只查 `SQLite`
- Celery backend 顶多做调试用途

### 3. 队列命名不清会让 worker 互串

建议固定：

- `orchestrator`
- `inference`

并给 task name 加完整 namespace：

- `minutes.orchestrator.prepare_job`
- `minutes.orchestrator.finalize_job`
- `minutes.inference.transcribe_job`

### 4. 迁移时不要同时重构 service 层

这是很典型的 Code Smell。

错误做法：

- 一边从 Dramatiq 切 Celery
- 一边改 service 逻辑
- 一边重构 repository

正确做法：

- 先只换任务执行框架
- 行为不变
- 跑通后再讨论架构优化

## 9. 测试迁移建议

### 必须保留的验证

- `tests/core`
  - 不应该受任务框架影响
- `tests/gateway`
  - 继续通过 fake dispatcher 隔离真实队列
- `tests/orchestrator`
  - 继续验证 `prepare -> transcribe -> finalize`

### 建议新增

- `tests/core/test_queue_dispatcher.py`
  - 验证 `CeleryQueueDispatcher` 会正确投递到目标 task
- `tests/integration/test_celery_worker_smoke.py`
  - 用 Redis + Celery worker 做最小集成验证

### 迁移完成前的验证顺序

1. `pytest -q`
2. 本地 fake inference 串行 smoke
3. 启 Celery worker
4. 手动发一个 job，看是否：
   - `prepare` 被消费
   - `transcribe` 被消费
   - `finalize` 被消费
   - `SQLite` 最终为 `completed`

## 10. 推荐的最小迁移方案

如果只是想“迁到 Celery，但别搞太重”，推荐最小方案：

- broker：`Redis`
- result backend：先不依赖
- 单一 Celery app
- 两个 worker 进程
  - `-Q orchestrator`
  - `-Q inference`
- 保持 `SQLite` 作为唯一业务状态源

这是当前仓库最稳的迁移路径。

## 11. 什么时候值得真的切 Celery

只有在下面场景里，Celery 的收益才会明显超过迁移成本：

- 任务编排明显变复杂
- 需要更成熟的 retry / ETA / schedule / workflow 能力
- 团队已经有 Celery 运维经验
- 后续要接 Flower 或更标准的 Celery 监控体系

如果只是“因为 Celery 更常见”，那不算一个足够好的迁移动机。

## 12. 给 Claude 的执行建议

如果 Claude 要实际做这次迁移，推荐按这个顺序推进：

1. 先新增 `docs/celery-migration.md` 之外的实现文件，不删旧 Dramatiq
2. 先让 `CeleryQueueDispatcher` 和 `celery_app.py` 落地
3. 再补 Celery task 文件
4. 跑 `pytest -q`
5. 再切 compose 和启动脚本
6. 最后删 Dramatiq 旧路径

不要一步到位“边删边改”，那样最容易把仓库带进半残状态。

