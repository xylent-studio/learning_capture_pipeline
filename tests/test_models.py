import pytest

from som_seedtalent_capture.models import (
    AudioTranscriptSegment,
    CaptureEvent,
    CaptureEventType,
    ContentChunk,
    ChunkType,
    PiiStatus,
    ReviewStatus,
    RightsStatus,
)


def test_note_event_requires_operator_note():
    with pytest.raises(ValueError):
        CaptureEvent(
            capture_session_id="session_fake",
            event_type=CaptureEventType.NOTE,
            timestamp_ms=100,
        )


def test_transcript_segment_end_must_be_after_start():
    with pytest.raises(ValueError):
        AudioTranscriptSegment(
            capture_session_id="session_fake",
            start_ms=100,
            end_ms=100,
            text="hello",
        )


def test_content_chunk_requires_source_citation():
    with pytest.raises(ValueError):
        ContentChunk(
            capture_session_id="session_fake",
            chunk_type=ChunkType.OCR,
            text="Visible text",
        )


def test_content_chunk_defaults_to_needs_review_and_unknown_rights():
    chunk = ContentChunk(
        capture_session_id="session_fake",
        chunk_type=ChunkType.TRANSCRIPT,
        text="Transcript text",
        source_start_ms=0,
        source_end_ms=1000,
    )
    assert chunk.review_status == ReviewStatus.NEEDS_REVIEW
    assert chunk.rights_status == RightsStatus.UNKNOWN
    assert not chunk.eligible_for_generation


def test_approved_known_rights_non_pii_chunk_is_generation_eligible():
    chunk = ContentChunk(
        capture_session_id="session_fake",
        chunk_type=ChunkType.TRANSCRIPT,
        text="Approved transcript text",
        source_start_ms=0,
        source_end_ms=1000,
        review_status=ReviewStatus.APPROVED,
        rights_status=RightsStatus.SEEDTALENT_AUTHORIZED_SCREEN_CAPTURE,
        pii_status=PiiStatus.NONE_DETECTED,
    )
    assert chunk.eligible_for_generation
