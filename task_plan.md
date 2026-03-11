# Task Plan

## Goal
Build a containerized backend for long-form speech-to-text with async jobs, SQLite metadata, Redis queue/events, ffmpeg preprocessing, and a GPU inference worker.

## Phases
- [x] Confirm stack and v1 scope
- [ ] Scaffold shared packages, compose, and tests
- [ ] Implement gateway API and sync adapter
- [ ] Implement orchestrator and inference workers
- [ ] Run smoke tests and fix issues

## Decisions
- Database: SQLite with WAL for low-concurrency single-host deployment
- Queue/events: Redis + Dramatiq
- Logging: Loguru JSON logs to stdout
- Media preprocessing: ffmpeg/ffprobe
- Profiles: `cn_meeting`, `multilingual_rich`

