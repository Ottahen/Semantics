"""Artifact packaging: bundle everything a task produced into one ZIP.

Used at the end of a `ctf` run to hand the user a single downloadable
file — the modified/created source files plus an optional manifest —
mirroring how the Completion screen advertises "Artifact created: ...".
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ArtifactManifest:
    task: str
    files_changed: list[str] = field(default_factory=list)
    model: Optional[str] = None
    tokens_used: int = 0
    duration_seconds: float = 0.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "task": self.task,
                "files_changed": self.files_changed,
                "model": self.model,
                "tokens_used": self.tokens_used,
                "duration_seconds": round(self.duration_seconds, 2),
            },
            indent=2,
        )


class ArtifactBuilder:
    """Stages files in a temp dir, then zips them up on demand."""

    def __init__(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="semantics_artifact_"))
        self._closed = False

    def add_file(self, relative_path: str, content: str) -> "ArtifactBuilder":
        self._check_open()
        file_path = self.temp_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return self

    def add_existing_file(self, source_path: Path, relative_path: Optional[str] = None) -> "ArtifactBuilder":
        self._check_open()
        source_path = Path(source_path)
        dest = self.temp_dir / (relative_path or source_path.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest)
        return self

    def add_manifest(self, manifest: ArtifactManifest, filename: str = "manifest.json") -> "ArtifactBuilder":
        return self.add_file(filename, manifest.to_json())

    def build_zip(self, output_path: Path | str = "artifact.zip") -> Path:
        self._check_open()
        zip_path = Path(output_path).resolve()
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in sorted(self.temp_dir.rglob("*")):
                if file_path.is_file():
                    zipf.write(file_path, file_path.relative_to(self.temp_dir))
        self.cleanup()
        return zip_path

    def cleanup(self) -> None:
        if not self._closed and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self._closed = True

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError("ArtifactBuilder already built/cleaned up; create a new one.")

    def __enter__(self) -> "ArtifactBuilder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()
