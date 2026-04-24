from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from som_seedtalent_capture.models import AudioTranscriptSegment


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
