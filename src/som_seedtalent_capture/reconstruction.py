from __future__ import annotations

from pydantic import BaseModel, Field

from som_seedtalent_capture.models import AudioTranscriptSegment, ChunkType, ContentChunk, PiiStatus, ReconstructedLesson, RightsStatus, ReviewStatus
from som_seedtalent_capture.pilot_manifests import PilotRunManifest
from som_seedtalent_capture.processing import OcrExtractionResult, TranscriptExtractionResult


class ReconstructionInputBundle(BaseModel):
    run_manifest: PilotRunManifest
    transcript_results: list[TranscriptExtractionResult] = Field(default_factory=list)
    ocr_results: list[OcrExtractionResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    rights_status: RightsStatus = RightsStatus.SEEDTALENT_CONTRACT_FULL_USE
    pii_status: PiiStatus = PiiStatus.NONE_DETECTED


class ReconstructionResult(BaseModel):
    lessons: list[ReconstructedLesson] = Field(default_factory=list)
    chunks: list[ContentChunk] = Field(default_factory=list)
    low_confidence_chunk_count: int = 0
    low_confidence_chunk_ids: list[str] = Field(default_factory=list)
    source_artifact_paths: list[str] = Field(default_factory=list)
    chunk_counts_by_type: dict[str, int] = Field(default_factory=dict)
    review_status_summary: dict[str, int] = Field(default_factory=dict)


def _summarize_chunks(chunks: list[ContentChunk]) -> tuple[dict[str, int], dict[str, int]]:
    chunk_counts = {
        chunk_type.value: sum(1 for chunk in chunks if chunk.chunk_type == chunk_type)
        for chunk_type in {chunk.chunk_type for chunk in chunks}
    }
    review_counts = {
        review_status.value: sum(1 for chunk in chunks if chunk.review_status == review_status)
        for review_status in {chunk.review_status for chunk in chunks}
    }
    return chunk_counts, review_counts


def reconstruct_from_input_bundle(bundle: ReconstructionInputBundle) -> ReconstructionResult:
    transcript_segments = [
        segment
        for transcript_result in bundle.transcript_results
        for segment in transcript_result.segments
    ]
    result = reconstruct_capture_outputs(
        capture_session_id=bundle.run_manifest.capture_session_id,
        course_title=bundle.run_manifest.course_title,
        lesson_title=bundle.run_manifest.course_title,
        transcript_segments=transcript_segments,
        ocr_results=bundle.ocr_results,
        rights_status=bundle.rights_status,
        pii_status=bundle.pii_status,
    )
    result.source_artifact_paths = sorted(
        {
            artifact.local_path
            for artifact in bundle.run_manifest.planned_artifacts
        }
    )
    result.chunk_counts_by_type, result.review_status_summary = _summarize_chunks(result.chunks)
    return result


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
    low_confidence_chunk_ids: list[str] = []

    for segment in transcript_segments:
        chunk = ContentChunk(
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
        chunks.append(chunk)
        if (segment.confidence or 0.0) < 0.6:
            low_confidence_chunk_count += 1
            low_confidence_chunk_ids.append(chunk.chunk_id)

    for index, result in enumerate(ocr_results):
        chunk = ContentChunk(
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
        chunks.append(chunk)
        if result.confidence < 0.6:
            low_confidence_chunk_count += 1
            low_confidence_chunk_ids.append(chunk.chunk_id)

    chunk_counts_by_type, review_status_summary = _summarize_chunks(chunks)

    return ReconstructionResult(
        lessons=[lesson],
        chunks=chunks,
        low_confidence_chunk_count=low_confidence_chunk_count,
        low_confidence_chunk_ids=low_confidence_chunk_ids,
        source_artifact_paths=sorted({result.image_uri for result in ocr_results}),
        chunk_counts_by_type=chunk_counts_by_type,
        review_status_summary=review_status_summary,
    )
