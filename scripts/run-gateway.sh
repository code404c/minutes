#!/usr/bin/env bash
set -euo pipefail

exec uvicorn minutes_gateway.app:create_app --factory --host "${MINUTES_HOST:-0.0.0.0}" --port "${MINUTES_PORT:-8000}"

