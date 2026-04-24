from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import RecorderProfile


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class RecorderSessionStatus(StrEnum):
    STARTED = "started"
    STOPPED = "stopped"


class RecorderStartRequest(BaseModel):
    artifact_root: str
    course_title: str
    recorder_profile: RecorderProfile


class RecorderSession(BaseModel):
    provider_name: str
    recorder_profile: RecorderProfile
    status: RecorderSessionStatus
    video_uri: str
    audio_uri: str | None = None
    planned_command: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=_now_utc)
    stopped_at: datetime | None = None


class RecorderProvider(Protocol):
    def start(self, request: RecorderStartRequest) -> RecorderSession:
        ...

    def stop(self, session: RecorderSession) -> RecorderSession:
        ...


class FakeRecorderProvider:
    def __init__(self, *, emit_audio_artifact: bool = True) -> None:
        self.emit_audio_artifact = emit_audio_artifact

    def start(self, request: RecorderStartRequest) -> RecorderSession:
        artifact_root = Path(request.artifact_root).resolve()
        recording_dir = artifact_root / "recordings"
        recording_dir.mkdir(parents=True, exist_ok=True)

        video_uri = str((recording_dir / "fixture-capture.mp4").resolve())
        Path(video_uri).touch()

        audio_uri = None
        if self.emit_audio_artifact:
            audio_uri = str((recording_dir / "fixture-audio.wav").resolve())
            Path(audio_uri).touch()

        return RecorderSession(
            provider_name="fake_recorder",
            recorder_profile=request.recorder_profile,
            status=RecorderSessionStatus.STARTED,
            video_uri=video_uri,
            audio_uri=audio_uri,
            metadata={"mode": "fake"},
        )

    def stop(self, session: RecorderSession) -> RecorderSession:
        return session.model_copy(update={"status": RecorderSessionStatus.STOPPED, "stopped_at": _now_utc()})


class FFmpegRecorderProvider:
    def start(self, request: RecorderStartRequest) -> RecorderSession:
        artifact_root = Path(request.artifact_root).resolve()
        recording_dir = artifact_root / "recordings"
        recording_dir.mkdir(parents=True, exist_ok=True)

        video_uri = str((recording_dir / "ffmpeg-capture.mp4").resolve())
        audio_uri = str((recording_dir / "ffmpeg-audio.wav").resolve())
        planned_command = [
            "ffmpeg",
            "-y",
            "-f",
            "gdigrab",
            "-i",
            "desktop",
            video_uri,
        ]
        return RecorderSession(
            provider_name="ffmpeg_recorder",
            recorder_profile=request.recorder_profile,
            status=RecorderSessionStatus.STARTED,
            video_uri=video_uri,
            audio_uri=audio_uri,
            planned_command=planned_command,
            metadata={"mode": "skeleton"},
        )

    def stop(self, session: RecorderSession) -> RecorderSession:
        return session.model_copy(update={"status": RecorderSessionStatus.STOPPED, "stopped_at": _now_utc()})


class ObsRecorderProvider:
    def start(self, request: RecorderStartRequest) -> RecorderSession:
        artifact_root = Path(request.artifact_root).resolve()
        recording_dir = artifact_root / "recordings"
        recording_dir.mkdir(parents=True, exist_ok=True)

        video_uri = str((recording_dir / "obs-capture.mkv").resolve())
        return RecorderSession(
            provider_name="obs_recorder",
            recorder_profile=request.recorder_profile,
            status=RecorderSessionStatus.STARTED,
            video_uri=video_uri,
            audio_uri=None,
            metadata={"mode": "skeleton", "scene": "SeedTalent Capture"},
        )

    def stop(self, session: RecorderSession) -> RecorderSession:
        return session.model_copy(update={"status": RecorderSessionStatus.STOPPED, "stopped_at": _now_utc()})
