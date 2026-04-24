from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from som_seedtalent_capture.models import ContentChunk, PiiStatus, ReviewStatus, RightsStatus


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class GovernanceBlockReason(StrEnum):
    UNKNOWN_RIGHTS = "unknown_rights"
    RESTRICTED_RIGHTS = "restricted_rights"
    REVIEW_NOT_APPROVED = "review_not_approved"
    POSSIBLE_PII = "possible_pii"
    CONTAINS_PII = "contains_pii"


class ChunkGovernanceDecision(BaseModel):
    eligible_for_search: bool
    eligible_for_generation: bool
    blocked_reasons: list[GovernanceBlockReason] = Field(default_factory=list)


class ReviewAuditRecord(BaseModel):
    reviewer: str
    target_type: str
    target_id: str
    previous_status: ReviewStatus
    new_status: ReviewStatus
    action: str
    timestamp: datetime = Field(default_factory=_now_utc)
    notes: str | None = None


def assess_chunk_governance(chunk: ContentChunk) -> ChunkGovernanceDecision:
    blocked_reasons: list[GovernanceBlockReason] = []

    if chunk.rights_status == RightsStatus.UNKNOWN:
        blocked_reasons.append(GovernanceBlockReason.UNKNOWN_RIGHTS)
    if chunk.rights_status == RightsStatus.RESTRICTED:
        blocked_reasons.append(GovernanceBlockReason.RESTRICTED_RIGHTS)
    if chunk.review_status != ReviewStatus.APPROVED:
        blocked_reasons.append(GovernanceBlockReason.REVIEW_NOT_APPROVED)
    if chunk.pii_status == PiiStatus.POSSIBLE_PII:
        blocked_reasons.append(GovernanceBlockReason.POSSIBLE_PII)
    if chunk.pii_status == PiiStatus.CONTAINS_PII:
        blocked_reasons.append(GovernanceBlockReason.CONTAINS_PII)

    eligible_for_search = len(blocked_reasons) == 0
    eligible_for_generation = len(blocked_reasons) == 0

    return ChunkGovernanceDecision(
        eligible_for_search=eligible_for_search,
        eligible_for_generation=eligible_for_generation,
        blocked_reasons=blocked_reasons,
    )


def record_review_decision(
    *,
    reviewer: str,
    target_type: str,
    target_id: str,
    previous_status: ReviewStatus,
    new_status: ReviewStatus,
    notes: str | None = None,
) -> ReviewAuditRecord:
    return ReviewAuditRecord(
        reviewer=reviewer,
        target_type=target_type,
        target_id=target_id,
        previous_status=previous_status,
        new_status=new_status,
        action=f"{previous_status.value}_to_{new_status.value}",
        notes=notes,
    )
