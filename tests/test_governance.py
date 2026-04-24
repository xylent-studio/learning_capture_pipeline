from som_seedtalent_capture.governance import GovernanceBlockReason, assess_chunk_governance, record_review_decision
from som_seedtalent_capture.models import ChunkType, ContentChunk, PiiStatus, ReviewStatus, RightsStatus


def _chunk(
    *,
    rights_status: RightsStatus = RightsStatus.SEEDTALENT_CONTRACT_FULL_USE,
    pii_status: PiiStatus = PiiStatus.NONE_DETECTED,
    review_status: ReviewStatus = ReviewStatus.APPROVED,
) -> ContentChunk:
    return ContentChunk(
        capture_session_id="session-123",
        chunk_type=ChunkType.TRANSCRIPT,
        text="Approved training content",
        source_start_ms=0,
        source_end_ms=1000,
        rights_status=rights_status,
        pii_status=pii_status,
        review_status=review_status,
    )


def test_assess_chunk_governance_allows_approved_authorized_chunk():
    decision = assess_chunk_governance(_chunk())

    assert decision.eligible_for_search is True
    assert decision.eligible_for_generation is True
    assert decision.blocked_reasons == []


def test_assess_chunk_governance_blocks_unknown_rights_and_pii():
    decision = assess_chunk_governance(
        _chunk(
            rights_status=RightsStatus.UNKNOWN,
            pii_status=PiiStatus.POSSIBLE_PII,
            review_status=ReviewStatus.NEEDS_REVIEW,
        )
    )

    assert decision.eligible_for_search is False
    assert decision.eligible_for_generation is False
    assert GovernanceBlockReason.UNKNOWN_RIGHTS in decision.blocked_reasons
    assert GovernanceBlockReason.POSSIBLE_PII in decision.blocked_reasons
    assert GovernanceBlockReason.REVIEW_NOT_APPROVED in decision.blocked_reasons


def test_record_review_decision_captures_transition():
    audit = record_review_decision(
        reviewer="reviewer@example.com",
        target_type="content_chunk",
        target_id="chunk-123",
        previous_status=ReviewStatus.NEEDS_REVIEW,
        new_status=ReviewStatus.APPROVED,
        notes="Approved for internal training use.",
    )

    assert audit.action == "needs_review_to_approved"
    assert audit.notes == "Approved for internal training use."
