#!/usr/bin/env bash
set -euo pipefail

exec dramatiq minutes_inference.actors --processes 1 --threads 1

