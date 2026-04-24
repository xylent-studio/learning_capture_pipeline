from som_seedtalent_capture.models import AudioTranscriptSegment, ReviewStatus
from som_seedtalent_capture.processing import OcrExtractionResult
from som_seedtalent_capture.reconstruction import reconstruct_capture_outputs


def test_reconstruct_capture_outputs_creates_cited_chunks_and_flags_low_confidence():
    result = reconstruct_capture_outputs(
        capture_session_id="session-123",
        course_title="Pilot Course",
        lesson_title="Lesson One",
        transcript_segments=[
            AudioTranscriptSegment(
                capture_session_id="session-123",
                start_ms=0,
                end_ms=1000,
                text="Transcript content",
                confidence=0.95,
            ),
            AudioTranscriptSegment(
                capture_session_id="session-123",
                start_ms=1000,
                end_ms=2000,
                text="Uncertain transcript content",
                confidence=0.4,
            ),
        ],
        ocr_results=[
            OcrExtractionResult(
                image_uri="C:/captures/frame-001.png",
                text="Visible slide text",
                confidence=0.5,
                provider_name="fake_ocr",
            )
        ],
        brand="State of Mind",
        jurisdiction="CA",
    )

    assert len(result.lessons) == 1
    assert len(result.chunks) == 3
    assert result.low_confidence_chunk_count == 2
    assert len(result.low_confidence_chunk_ids) == 2
    assert all(chunk.review_status == ReviewStatus.NEEDS_REVIEW for chunk in result.chunks)
    assert any(chunk.source_screenshot_uri for chunk in result.chunks)
    assert result.chunk_counts_by_type["transcript"] == 2
    assert result.chunk_counts_by_type["ocr"] == 1
