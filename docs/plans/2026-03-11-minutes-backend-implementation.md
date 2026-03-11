# Minutes Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first backend slice of a Feishu Minutes-like speech-to-text service with async jobs, container deployment, and smoke-test coverage.

**Architecture:** Single-host compose deployment with a public FastAPI gateway, a CPU orchestrator worker for ffmpeg preprocessing/finalization, and a GPU inference worker for ASR. Shared state lives in SQLite and Redis.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, SQLite, Redis, Dramatiq, Loguru, ffmpeg/ffprobe, FunASR/ModelScope, Docker Compose

