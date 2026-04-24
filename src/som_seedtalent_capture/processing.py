from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from som_seedtalent_capture.artifacts import ArtifactKind, ArtifactRecord
from som_seedtalent_capture.models import AudioTranscriptSegment
from som_seedtalent_capture.pilot_manifests import PilotRunManifest


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class OcrExtractionResult(BaseModel):
    image_uri: str
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    provider_name: str
    notes: str | None = None


class TranscriptExtractionResult(BaseModel):
    audio_uri: str
    segments: list[AudioTranscriptSegment] = Field(default_factory=list)
    provider_name: str
    notes: str | None = None


class OcrWorkItem(BaseModel):
    capture_session_id: str
    source_artifact_path: str
    provider_name: str
    output_artifact_path: str
    notes: str | None = None


class TranscriptWorkItem(BaseModel):
    capture_session_id: str
    source_artifact_path: str
    provider_name: str
    output_artifact_path: str
    notes: str | None = None


class ProcessingManifest(BaseModel):
    run_id: str
    capture_session_id: str
    status: ProcessingStatus = ProcessingStatus.PENDING
    ocr_work_items: list[OcrWorkItem] = Field(default_factory=list)
    transcript_work_items: list[TranscriptWorkItem] = Field(default_factory=list)
    output_artifacts: list[ArtifactRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProcessingBundleResult(BaseModel):
    manifest: ProcessingManifest
    ocr_results: list[OcrExtractionResult] = Field(default_factory=list)
    transcript_results: list[TranscriptExtractionResult] = Field(default_factory=list)
    status: ProcessingStatus = ProcessingStatus.PENDING


class OcrProvider(Protocol):
    def extract(self, image_uri: str) -> OcrExtractionResult:
        ...


class TranscriptionProvider(Protocol):
    def transcribe(self, audio_uri: str, *, capture_session_id: str) -> TranscriptExtractionResult:
        ...


class FakeOcrProvider:
    def __init__(self, *, text: str = "Fake OCR text", confidence: float = 0.99) -> None:
        self._text = text
        self._confidence = confidence

    def extract(self, image_uri: str) -> OcrExtractionResult:
        return OcrExtractionResult(
            image_uri=image_uri,
            text=self._text,
            confidence=self._confidence,
            provider_name="fake_ocr",
        )


class LocalOcrStubProvider:
    def extract(self, image_uri: str) -> OcrExtractionResult:
        stem = Path(image_uri).stem.replace("-", " ")
        return OcrExtractionResult(
            image_uri=image_uri,
            text=f"OCR stub output for {stem}",
            confidence=0.35,
            provider_name="local_ocr_stub",
            notes="Local OCR implementation not wired yet.",
        )


class FakeTranscriptionProvider:
    def __init__(self, *, text: str = "Fake transcript text", confidence: float = 0.98) -> None:
        self._text = text
        self._confidence = confidence

    def transcribe(self, audio_uri: str, *, capture_session_id: str) -> TranscriptExtractionResult:
        return TranscriptExtractionResult(
            audio_uri=audio_uri,
            provider_name="fake_transcription",
            segments=[
                AudioTranscriptSegment(
                    capture_session_id=capture_session_id,
                    start_ms=0,
                    end_ms=1000,
                    text=self._text,
                    confidence=self._confidence,
                )
            ],
        )


class LocalTranscriptionStubProvider:
    def transcribe(self, audio_uri: str, *, capture_session_id: str) -> TranscriptExtractionResult:
        stem = Path(audio_uri).stem.replace("-", " ")
        return TranscriptExtractionResult(
            audio_uri=audio_uri,
            provider_name="local_transcription_stub",
            notes="Local transcription implementation not wired yet.",
            segments=[
                AudioTranscriptSegment(
                    capture_session_id=capture_session_id,
                    start_ms=0,
                    end_ms=1000,
                    text=f"Transcription stub output for {stem}",
                    confidence=0.3,
                )
            ],
        )


def build_processing_manifest(run_manifest: PilotRunManifest) -> ProcessingManifest:
    artifact_by_kind = {artifact.kind: artifact for artifact in run_manifest.planned_artifacts}
    ocr_items: list[OcrWorkItem] = []
    transcript_items: list[TranscriptWorkItem] = []

    screenshot_folder = artifact_by_kind.get(ArtifactKind.SCREENSHOT_FOLDER)
    if screenshot_folder is not None:
        ocr_output = artifact_by_kind.get(ArtifactKind.OCR_OUTPUT)
        ocr_items.append(
            OcrWorkItem(
                capture_session_id=run_manifest.capture_session_id,
                source_artifact_path=screenshot_folder.local_path,
                provider_name="local_ocr_stub",
                output_artifact_path=ocr_output.local_path if ocr_output else screenshot_folder.local_path,
                notes="Run through OCR after live capture artifacts exist.",
            )
        )

    audio_recording = artifact_by_kind.get(ArtifactKind.AUDIO_RECORDING)
    if audio_recording is not None:
        transcript_output = artifact_by_kind.get(ArtifactKind.TRANSCRIPT_OUTPUT)
        transcript_items.append(
            TranscriptWorkItem(
                capture_session_id=run_manifest.capture_session_id,
                source_artifact_path=audio_recording.local_path,
                provider_name="local_transcription_stub",
                output_artifact_path=transcript_output.local_path if transcript_output else audio_recording.local_path,
                notes="Run through transcription after live capture artifacts exist.",
            )
        )

    output_artifacts = [
        artifact for artifact in run_manifest.planned_artifacts if artifact.kind in {ArtifactKind.OCR_OUTPUT, ArtifactKind.TRANSCRIPT_OUTPUT}
    ]

    notes = ["Processing manifest created from planned artifacts."]
    if not run_manifest.runner_executed:
        notes.append("Runner has not executed yet; work items are placeholders.")

    return ProcessingManifest(
        run_id=run_manifest.run_id,
        capture_session_id=run_manifest.capture_session_id,
        status=ProcessingStatus.PENDING,
        ocr_work_items=ocr_items,
        transcript_work_items=transcript_items,
        output_artifacts=output_artifacts,
        notes=notes,
    )
