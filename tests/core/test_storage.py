from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import UploadFile

from minutes_core.config import Settings
from minutes_core.storage import StorageManager


@pytest.mark.parametrize(
    "raw_filename,expected_name",
    [
        ("../../etc/passwd", "passwd"),
        (r"C:\temp\meetings\demo.wav", "demo.wav"),
    ],
    ids=["posix-traversal", "windows-backslash"],
)
def test_storage_manager_sanitizes_filename(tmp_path, raw_filename: str, expected_name: str) -> None:
    settings = Settings(storage_root=tmp_path, database_url="sqlite://", redis_url="redis://unused:6379/0")
    manager = StorageManager(settings)

    upload = UploadFile(filename=raw_filename, file=BytesIO(b"fake-audio"))
    source_path, _artifact_dir = manager.save_upload(upload, job_id="job-1")

    assert source_path.name == expected_name
    assert source_path.read_bytes() == b"fake-audio"
    assert source_path.parent == settings.uploads_dir / "job-1"
