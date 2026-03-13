#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from minutes_core.config import Settings
from minutes_core.db import create_session_factory, init_database
from minutes_core.events import EventBus
from minutes_core.profiles import resolve_profile
from minutes_core.queue import QueueDispatcher
from minutes_core.repositories import JobRepository
from minutes_core.schemas import JobCreate
from minutes_inference.service import InferenceService
from minutes_orchestrator.services import OrchestratorService


class NoopEventBus(EventBus):
    def __init__(self) -> None:
        self.redis_url = "redis://unused"

    def publish(self, event) -> None:  # type: ignore[override]
        print(f"[event] {event.stage} {event.status} {event.progress}% {event.message}")


class InlineQueueDispatcher(QueueDispatcher):
    def enqueue_prepare_job(self, job_id: str) -> None:
        return None

    def enqueue_finalize_job(self, job_id: str) -> None:
        return None

    def enqueue_transcription_job(self, job_id: str) -> None:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local sequential transcription job without containers.")
    parser.add_argument("media_path", type=Path, help="Path to the input audio/video file.")
    parser.add_argument("--profile", default="cn_meeting", help="Job profile: cn_meeting or multilingual_rich.")
    parser.add_argument("--storage-root", type=Path, default=Path(".local-run"), help="Local storage root.")
    parser.add_argument("--database-path", type=Path, default=Path(".local-run/app.db"), help="SQLite DB path.")
    parser.add_argument("--fake-inference", action="store_true", help="Use fake inference for quick smoke runs.")
    parser.add_argument("--language", default=None, help="Override language.")
    parser.add_argument("--stt-base-url", default="http://localhost:8101", help="STT service base URL.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.media_path.exists():
        parser.error(f"Media file does not exist: {args.media_path}")

    settings = Settings(
        storage_root=args.storage_root,
        database_url=f"sqlite:///{args.database_path}",
        redis_url="redis://unused:6379/0",
        fake_inference=args.fake_inference,
        stt_base_url=args.stt_base_url,
    )
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    args.database_path.parent.mkdir(parents=True, exist_ok=True)

    session_factory = create_session_factory(settings)
    init_database(session_factory.kw["bind"])
    event_bus = NoopEventBus()
    queue_dispatcher = InlineQueueDispatcher()

    artifacts_dir = settings.artifacts_dir / str(uuid.uuid4())
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with session_factory() as session:
        repository = JobRepository(session)
        detail = repository.create_job(
            JobCreate(
                job_id=artifacts_dir.name,
                source_filename=args.media_path.name,
                source_content_type=None,
                source_path=str(args.media_path),
                output_dir=str(artifacts_dir),
                profile=resolve_profile(args.profile),
                language=args.language,
            )
        )
        session.commit()

    orchestrator = OrchestratorService(
        settings=settings,
        session_factory=session_factory,
        event_bus=event_bus,
        queue_dispatcher=queue_dispatcher,
    )
    inference = InferenceService(
        settings=settings,
        session_factory=session_factory,
        event_bus=event_bus,
        queue_dispatcher=queue_dispatcher,
    )

    orchestrator.prepare_job(detail.id)
    inference.transcribe_job(detail.id)

    with session_factory() as session:
        after_inference = JobRepository(session).get_job(detail.id)
        if after_inference is None:
            print("Job disappeared after inference.", file=sys.stderr)
            return 1
        if after_inference.status == "failed" or str(after_inference.status) == "failed":
            print(f"job_id={after_inference.id}", file=sys.stderr)
            print(f"status={after_inference.status}", file=sys.stderr)
            print(f"error_code={after_inference.error_code}", file=sys.stderr)
            print(f"error_message={after_inference.error_message}", file=sys.stderr)
            return 1

    orchestrator.finalize_job(detail.id)

    with session_factory() as session:
        final_detail = JobRepository(session).get_job(detail.id)
        if final_detail is None or final_detail.result is None:
            print("Job finished without a transcript result.", file=sys.stderr)
            return 1

        print(f"job_id={final_detail.id}")
        print(f"status={final_detail.status}")
        print(f"normalized_path={final_detail.normalized_path}")
        print(f"artifacts_dir={artifacts_dir}")
        print("transcript_preview:")
        print(final_detail.result.full_text[:1000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
