#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
from collections.abc import Iterable
from pathlib import Path

from minutes_core.config import Settings
from minutes_core.profiles import get_profile_spec


def _resolve_snapshot_download():
    candidates = [
        ("modelscope", "snapshot_download"),
        ("modelscope.hub.snapshot_download", "snapshot_download"),
    ]
    for module_name, attribute in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        snapshot_download = getattr(module, attribute, None)
        if callable(snapshot_download):
            return snapshot_download
    raise RuntimeError(
        "ModelScope is not installed. Run `uv sync --extra dev --extra inference` before downloading models."
    )


def _iter_model_ids(profiles: Iterable[str]) -> list[str]:
    model_ids: list[str] = []
    for profile_name in profiles:
        profile = get_profile_spec(profile_name)
        for model_id in (
            profile.asr_model_id,
            profile.vad_model_id,
            profile.punc_model_id,
            profile.speaker_model_id,
        ):
            if model_id and model_id not in model_ids:
                model_ids.append(model_id)
    return model_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and warm the FunASR model dependencies used by Minutes.")
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        default=None,
        help="Profile to pre-download. May be passed multiple times.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Override the ModelScope cache directory. Defaults to MINUTES_MODEL_CACHE_DIR.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = Settings()
    cache_dir = args.cache_dir or settings.model_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    snapshot_download = _resolve_snapshot_download()
    profiles = args.profiles or ["cn_meeting", "multilingual_rich"]
    model_ids = _iter_model_ids(profiles)

    print(f"cache_dir={cache_dir}")
    for model_id in model_ids:
        print(f"downloading={model_id}")
        target = snapshot_download(model_id, cache_dir=str(cache_dir))
        print(f"downloaded={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
