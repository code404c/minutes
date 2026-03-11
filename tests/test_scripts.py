from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_download_models_module():  # type: ignore[no-untyped-def]
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "download_models.py"
    spec = importlib.util.spec_from_file_location("download_models", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_download_models_profile_flag_overrides_default_profiles() -> None:
    module = _load_download_models_module()
    parser = module.build_parser()

    args = parser.parse_args(["--profile", "cn_meeting"])

    assert args.profiles == ["cn_meeting"]
