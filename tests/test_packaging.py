from __future__ import annotations

from pathlib import Path


def test_all_dockerfiles_copy_readme_for_package_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    dockerfiles = [
        root / "docker" / "gateway.Dockerfile",
        root / "docker" / "orchestrator.Dockerfile",
        root / "docker" / "inference-worker.Dockerfile",
    ]

    for dockerfile in dockerfiles:
        content = dockerfile.read_text(encoding="utf-8")
        assert "COPY README.md /app/README.md" in content, dockerfile
