from __future__ import annotations

from pydantic import BaseModel, Field

from som_seedtalent_capture.models import AudioTranscriptSegment, ChunkType, ContentChunk, PiiStatus, ReconstructedLesson, RightsStatus, ReviewStatus
from som_seedtalent_capture.processing import OcrExtractionResult


class ReconstructionResult(BaseModel):
    lessons: list[ReconstructedLesson] = Field(default_factory=list)
    chunks: list[ContentChunk] = Field(default_factory=list)
    low_confidence_chunk_count: int = 0


def reconstruct_capture_outputs(
    *,
    capture_session_id: str,
    course_title: str,
    lesson_title: str,
    transcript_segments: list[AudioTranscriptSegment],
    ocr_results: list[OcrExtractionResult],
    brand: str | None = None,
    jurisdiction: str | None = None,
    rights_status: RightsStatus = RightsStatus.SEEDTALENT_CONTRACT_FULL_USE,
    pii_status: PiiStatus = PiiStatus.NONE_DETECTED,
) -> ReconstructionResult:
    lesson_start_ms = 0
    lesson_end_ms = max(
        [segment.end_ms for segment in transcript_segments] + [1000 * max(len(ocr_results), 1)]
    )
    lesson = ReconstructedLesson(
        capture_session_id=capture_session_id,
        course_title=course_title,
        lesson_title=lesson_title,
        lesson_order=0,
        summary=transcript_segments[0].text if transcript_segments else (ocr_results[0].text if ocr_results else None),
        source_start_ms=lesson_start_ms,
        source_end_ms=lesson_end_ms,
    )

    chunks: list[ContentChunk] = []
    low_confidence_chunk_count = 0

    for segment in transcript_segments:
        chunks.append(
            ContentChunk(
                capture_session_id=capture_session_id,
                lesson_id=lesson.lesson_id,
                chunk_type=ChunkType.TRANSCRIPT,
                text=segment.text,
                source_start_ms=segment.start_ms,
                source_end_ms=segment.end_ms,
                brand=brand,
                jurisdiction=jurisdiction,
                rights_status=rights_status,
                pii_status=pii_status,
                review_status=ReviewStatus.NEEDS_REVIEW,
            )
        )
        if (segment.confidence or 0.0) < 0.6:
            low_confidence_chunk_count += 1

    for index, result in enumerate(ocr_results):
        chunks.append(
            ContentChunk(
                capture_session_id=capture_session_id,
                lesson_id=lesson.lesson_id,
                chunk_type=ChunkType.OCR,
                text=result.text,
                source_screenshot_uri=result.image_uri,
                source_start_ms=index * 1000,
                source_end_ms=(index + 1) * 1000,
                brand=brand,
                jurisdiction=jurisdiction,
                rights_status=rights_status,
                pii_status=pii_status,
                review_status=ReviewStatus.NEEDS_REVIEW,
            )
        )
        if result.confidence < 0.6:
            low_confidence_chunk_count += 1

    return ReconstructionResult(
        lessons=[lesson],
        chunks=chunks,
        low_confidence_chunk_count=low_confidence_chunk_count,
    )
