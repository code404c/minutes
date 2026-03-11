from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from minutes_core.config import Settings


class StorageManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def create_job_paths(self, filename: str, *, job_id: str | None = None) -> tuple[Path, Path]:
        job_id = job_id or str(uuid.uuid4())
        upload_dir = self.settings.uploads_dir / job_id
        artifact_dir = self.settings.artifacts_dir / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        source_path = upload_dir / filename
        return source_path, artifact_dir

    def save_upload(self, upload: UploadFile, *, job_id: str | None = None) -> tuple[Path, Path]:
        filename = upload.filename or "upload.bin"
        source_path, artifact_dir = self.create_job_paths(filename, job_id=job_id)
        with source_path.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        return source_path, artifact_dir
