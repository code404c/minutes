#!/usr/bin/env python3
"""CI 环境自检脚本。"""

from __future__ import annotations

import shutil
import sys


def main() -> int:
    ok = True

    # Python version
    vi = sys.version_info
    if vi >= (3, 12):
        print(f"[PASS] Python >= 3.12 ({vi.major}.{vi.minor}.{vi.micro})")
    else:
        print(f"[FAIL] Python >= 3.12 required (found {vi.major}.{vi.minor}.{vi.micro})")
        ok = False

    # ffmpeg
    path = shutil.which("ffmpeg")
    if path:
        print(f"[PASS] ffmpeg found: {path}")
    else:
        print("[FAIL] ffmpeg not found")
        ok = False

    # ffprobe
    path = shutil.which("ffprobe")
    if path:
        print(f"[PASS] ffprobe found: {path}")
    else:
        print("[FAIL] ffprobe not found")
        ok = False

    # uv
    path = shutil.which("uv")
    if path:
        print(f"[PASS] uv found: {path}")
    else:
        print("[FAIL] uv not found")
        ok = False

    # Disk space
    usage = shutil.disk_usage(".")
    free_gb = usage.free / (1024**3)
    if free_gb >= 1.0:
        print(f"[PASS] Disk free space: {free_gb:.1f} GB (>= 1 GB)")
    else:
        print(f"[FAIL] Disk free space: {free_gb:.1f} GB (< 1 GB)")
        ok = False

    print()
    if ok:
        print("All checks passed.")
    else:
        print("Some checks failed.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
