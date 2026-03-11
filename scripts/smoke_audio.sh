#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-fake}"
AUDIO_INPUT="${2:-}"
DEVICE="${DEVICE:-cuda:0}"

if [[ -z "${AUDIO_INPUT}" ]]; then
  echo "usage: scripts/smoke_audio.sh <fake|real> <audio-path-or-directory>" >&2
  exit 1
fi

audio_path="${AUDIO_INPUT}"
if [[ "${audio_path}" =~ ^[A-Za-z]:\\ ]]; then
  audio_path="$(wslpath -u "${audio_path}")"
fi

if [[ -d "${audio_path}" ]]; then
  audio_path="$(
    find "${audio_path}" -maxdepth 1 -type f \
      \( -iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a' -o -iname '*.flac' -o -iname '*.ogg' \) \
      | sort \
      | head -n 1
  )"
fi

if [[ -z "${audio_path}" || ! -f "${audio_path}" ]]; then
  echo "audio file not found: ${AUDIO_INPUT}" >&2
  exit 1
fi

cmd=(uv run python scripts/local_run_job.py)
if [[ "${MODE}" == "fake" ]]; then
  cmd+=(--fake-inference)
elif [[ "${MODE}" == "real" ]]; then
  cmd+=(--device "${DEVICE}")
else
  echo "unsupported mode: ${MODE}" >&2
  exit 1
fi
cmd+=("${audio_path}")

printf 'running:'
printf ' %q' "${cmd[@]}"
printf '\n'
"${cmd[@]}"
