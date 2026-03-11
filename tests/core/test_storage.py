from __future__ import annotations

from io import BytesIO

from fastapi import UploadFile

from minutes_core.config import Settings
from minutes_core.storage import StorageManager


def test_storage_manager_sanitizes_posix_style_filename(tmp_path) -> None:
    settings = Settings(storage_root=tmp_path, database_url="sqlite://", redis_url="redis://unused:6379/0")
    manager = StorageManager(settings)

    upload = UploadFile(filename="../../etc/passwd", file=BytesIO(b"fake-audio"))
    source_path, _artifact_dir = manager.save_upload(upload, job_id="job-1")

    assert source_path.name == "passwd"
    assert source_path.read_bytes() == b"fake-audio"
    assert source_path.parent == settings.uploads_dir / "job-1"


def test_storage_manager_sanitizes_windows_style_filename(tmp_path) -> None:
    settings = Settings(storage_root=tmp_path, database_url="sqlite://", redis_url="redis://unused:6379/0")
    manager = StorageManager(settings)

    upload = UploadFile(filename=r"C:\temp\meetings\demo.wav", file=BytesIO(b"fake-audio"))
    source_path, _artifact_dir = manager.save_upload(upload, job_id="job-2")

    assert source_path.name == "demo.wav"
    assert source_path.read_bytes() == b"fake-audio"
    assert source_path.parent == settings.uploads_dir / "job-2"
