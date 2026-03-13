from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "dockerfile_name",
    [
        "gateway.Dockerfile",
        "orchestrator.Dockerfile",
        "inference-worker.Dockerfile",
    ],
    ids=["gateway", "orchestrator", "inference-worker"],
)
def test_dockerfile_copies_readme_for_package_metadata(dockerfile_name: str) -> None:
    root = Path(__file__).resolve().parents[1]
    dockerfile = root / "docker" / dockerfile_name
    content = dockerfile.read_text(encoding="utf-8")
    assert "COPY README.md /app/README.md" in content, dockerfile
