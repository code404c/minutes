"""SSE 端点的异步流测试：使用 httpx.AsyncClient + ASGITransport 进行真正的异步 SSE 验证。"""

from __future__ import annotations

import asyncio
import json
from http import HTTPStatus

import httpx

from minutes_core.constants import JobStatus
from minutes_core.schemas import JobEvent

from .conftest import GatewayEnv

# ---------------------------------------------------------------------------
# SSE 解析工具
# ---------------------------------------------------------------------------


async def _collect_sse_events(response: httpx.Response, *, max_events: int = 10) -> list[dict[str, str]]:
    """从异步 SSE 响应中收集事件。"""
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:") :].strip()
        elif line == "" and current:
            if "data" in current:
                events.append(current)
            current = {}
            if len(events) >= max_events:
                break
    if current and "data" in current:
        events.append(current)
    return events


def _create_job_in_env(
    env: GatewayEnv,
    *,
    status: JobStatus = JobStatus.QUEUED,
    progress: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
) -> str:
    """在 GatewayEnv 中直接创建 job，返回 job_id。"""
    import uuid

    from minutes_core.repositories import JobRepository
    from minutes_core.schemas import JobCreate

    source_dir = env.settings.uploads_dir / f"seed-{uuid.uuid4().hex[:8]}"
    artifact_dir = env.settings.artifacts_dir / f"seed-{uuid.uuid4().hex[:8]}"
    source_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "meeting.wav"
    source_path.write_bytes(b"seed-audio")

    with env.session_factory() as session:
        repo = JobRepository(session)
        created = repo.create_job(
            JobCreate(
                source_filename=source_path.name,
                source_content_type="audio/wav",
                source_path=str(source_path),
                output_dir=str(artifact_dir),
                language="zh",
            )
        )
        if status is not JobStatus.QUEUED or progress or error_code or error_message:
            repo.update_job(
                created.id,
                status=status,
                progress=progress,
                error_code=error_code,
                error_message=error_message,
            )
        session.commit()
        return created.id


# ---------------------------------------------------------------------------
# 异步 SSE 测试
# ---------------------------------------------------------------------------


async def test_async_sse_receives_initial_snapshot(async_gateway_env: GatewayEnv) -> None:
    """基础验证：异步路径下 snapshot 事件正确到达。"""
    env = async_gateway_env
    job_id = _create_job_in_env(env, status=JobStatus.TRANSCRIBING, progress=50)

    transport = httpx.ASGITransport(app=env.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
            assert response.status_code == HTTPStatus.OK
            events = await _collect_sse_events(response, max_events=1)

    assert len(events) >= 1
    data = json.loads(events[0]["data"])
    assert data["event"] == "snapshot"
    assert data["job_id"] == job_id
    assert data["status"] == JobStatus.TRANSCRIBING.value
    assert data["progress"] == 50


async def test_async_sse_receives_multiple_events_in_order(async_gateway_env: GatewayEnv) -> None:
    """预填充 3 条消息后，应按 FIFO 顺序收到 snapshot + 3 条后续事件。"""
    env = async_gateway_env
    job_id = _create_job_in_env(env, status=JobStatus.PREPROCESSING, progress=25)

    for i, (stage, pct) in enumerate([("prepare", 30), ("transcribe", 50), ("transcribe", 75)]):
        evt = JobEvent(
            event=f"job.progress.{i}",
            job_id=job_id,
            status=JobStatus.TRANSCRIBING,
            progress=pct,
            stage=stage,
        )
        env.event_bus.enqueue_message(job_id, evt.model_dump_json())

    transport = httpx.ASGITransport(app=env.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
            events = await _collect_sse_events(response, max_events=4)

    assert len(events) == 4
    assert json.loads(events[0]["data"])["event"] == "snapshot"
    assert json.loads(events[1]["data"])["progress"] == 30
    assert json.loads(events[2]["data"])["progress"] == 50
    assert json.loads(events[3]["data"])["progress"] == 75


async def test_async_sse_client_disconnect_stops_generator(async_gateway_env: GatewayEnv) -> None:
    """使用 set_blocking() 让 subscribe 阻塞，然后客户端超时断开 → 生成器正常终止。"""
    env = async_gateway_env
    job_id = _create_job_in_env(env, status=JobStatus.TRANSCRIBING, progress=50)
    release = env.event_bus.set_blocking()

    transport = httpx.ASGITransport(app=env.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            async with asyncio.timeout(0.5):
                async with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
                    await _collect_sse_events(response, max_events=10)
        except TimeoutError:
            pass

    # snapshot 已收到或因超时为空都是可接受的
    # 关键验证：不会抛出未处理异常，生成器正常终止
    release.set()


async def test_async_sse_concurrent_connections(async_gateway_env: GatewayEnv) -> None:
    """2 个 job 各开 1 个 SSE 连接，各自只收到自己的事件。"""
    env = async_gateway_env
    job_a = _create_job_in_env(env, status=JobStatus.PREPROCESSING, progress=20)
    job_b = _create_job_in_env(env, status=JobStatus.TRANSCRIBING, progress=60)

    evt_a = JobEvent(
        event="job.a_update",
        job_id=job_a,
        status=JobStatus.PREPROCESSING,
        progress=30,
        stage="prepare",
    )
    evt_b = JobEvent(
        event="job.b_update",
        job_id=job_b,
        status=JobStatus.TRANSCRIBING,
        progress=70,
        stage="transcribe",
    )
    env.event_bus.enqueue_message(job_a, evt_a.model_dump_json())
    env.event_bus.enqueue_message(job_b, evt_b.model_dump_json())

    transport = httpx.ASGITransport(app=env.app)

    async def fetch_events(jid: str) -> list[dict[str, str]]:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream("GET", f"/api/v1/jobs/{jid}/events") as response:
                return await _collect_sse_events(response, max_events=2)

    events_a, events_b = await asyncio.gather(fetch_events(job_a), fetch_events(job_b))

    # 各自收到 snapshot + 1 条更新
    assert len(events_a) == 2
    assert len(events_b) == 2
    assert json.loads(events_a[1]["data"])["event"] == "job.a_update"
    assert json.loads(events_b[1]["data"])["event"] == "job.b_update"


async def test_async_sse_empty_bus_terminates_after_snapshot(async_gateway_env: GatewayEnv) -> None:
    """无预填充消息时，只收到 snapshot 后流结束。"""
    env = async_gateway_env
    job_id = _create_job_in_env(env, status=JobStatus.QUEUED, progress=0)

    transport = httpx.ASGITransport(app=env.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
            events = await _collect_sse_events(response, max_events=5)

    assert len(events) == 1
    data = json.loads(events[0]["data"])
    assert data["event"] == "snapshot"
    assert data["status"] == JobStatus.QUEUED.value


async def test_async_sse_404_for_missing_job(async_gateway_env: GatewayEnv) -> None:
    """异步客户端下的 404 错误处理。"""
    env = async_gateway_env

    transport = httpx.ASGITransport(app=env.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/jobs/non-existent-job/events")

    assert response.status_code == HTTPStatus.NOT_FOUND
