from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


def _slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    return slug or "artifact"


class ArtifactKind(StrEnum):
    SCREEN_RECORDING = "screen_recording"
    AUDIO_RECORDING = "audio_recording"
    SCREENSHOT = "screenshot"
    PREFLIGHT_CAPTURE = "preflight_capture"
    QA_REPORT = "qa_report"
    OCR_OUTPUT = "ocr_output"
    TRANSCRIPT_OUTPUT = "transcript_output"
    DIAGNOSTIC_SNAPSHOT = "diagnostic_snapshot"


class ArtifactRecord(BaseModel):
    kind: ArtifactKind
    local_path: str
    relative_path: str
    metadata: dict[str, str] = Field(default_factory=dict)


class RunArtifactLayout(BaseModel):
    batch_root: str
    run_root: str
    recordings_dir: str
    screenshots_dir: str
    preflight_dir: str
    qa_dir: str
    processing_dir: str
    diagnostics_dir: str


class ArtifactStore(Protocol):
    def ensure_run_layout(self, *, batch_id: str, run_id: str, course_title: str) -> RunArtifactLayout:
        ...

    def build_record(self, *, layout: RunArtifactLayout, kind: ArtifactKind, name: str, extension: str) -> ArtifactRecord:
        ...


class LocalArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()

    def ensure_run_layout(self, *, batch_id: str, run_id: str, course_title: str) -> RunArtifactLayout:
        course_slug = _slugify(course_title)
        batch_root = self._root / batch_id
        run_root = batch_root / f"{run_id}-{course_slug}"
        directories = {
            "recordings_dir": run_root / "recordings",
            "screenshots_dir": run_root / "screenshots",
            "preflight_dir": run_root / "preflight",
            "qa_dir": run_root / "qa",
            "processing_dir": run_root / "processing",
            "diagnostics_dir": run_root / "diagnostics",
        }
        for directory in directories.values():
            directory.mkdir(parents=True, exist_ok=True)

        return RunArtifactLayout(
            batch_root=str(batch_root.resolve()),
            run_root=str(run_root.resolve()),
            **{name: str(path.resolve()) for name, path in directories.items()},
        )

    def build_record(self, *, layout: RunArtifactLayout, kind: ArtifactKind, name: str, extension: str) -> ArtifactRecord:
        directory_map = {
            ArtifactKind.SCREEN_RECORDING: Path(layout.recordings_dir),
            ArtifactKind.AUDIO_RECORDING: Path(layout.recordings_dir),
            ArtifactKind.SCREENSHOT: Path(layout.screenshots_dir),
            ArtifactKind.PREFLIGHT_CAPTURE: Path(layout.preflight_dir),
            ArtifactKind.QA_REPORT: Path(layout.qa_dir),
            ArtifactKind.OCR_OUTPUT: Path(layout.processing_dir),
            ArtifactKind.TRANSCRIPT_OUTPUT: Path(layout.processing_dir),
            ArtifactKind.DIAGNOSTIC_SNAPSHOT: Path(layout.diagnostics_dir),
        }
        directory = directory_map[kind]
        local_path = directory / f"{_slugify(name)}.{extension.lstrip('.')}"
        relative_path = local_path.relative_to(Path(layout.batch_root).parent)
        return ArtifactRecord(
            kind=kind,
            local_path=str(local_path.resolve()),
            relative_path=str(relative_path),
            metadata={"directory": directory.name},
        )
