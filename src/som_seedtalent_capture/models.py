from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SourcePlatform(StrEnum):
    SEEDTALENT = "seedtalent"
    STATE_OF_MIND = "state_of_mind"
    OTHER = "other"


class CaptureMode(StrEnum):
    AUTHORIZED_SCREEN_CAPTURE = "authorized_screen_capture"
    AUTONOMOUS_UI_CAPTURE = "autonomous_ui_capture"
    VISIBLE_DOM_CAPTURE = "visible_dom_capture"
    MANUAL_UPLOAD = "manual_upload"
    UI_VISIBLE_EXPORT = "ui_visible_export"


class CaptureStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_RECAPTURE = "needs_recapture"


class ReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESTRICTED = "restricted"
    NEEDS_RECAPTURE = "needs_recapture"
    PII_ISSUE = "pii_issue"
    RIGHTS_ISSUE = "rights_issue"


class RightsStatus(StrEnum):
    SEEDTALENT_AUTHORIZED_SCREEN_CAPTURE = "seedtalent_authorized_screen_capture"
    SEEDTALENT_CONTRACT_FULL_USE = "seedtalent_contract_full_use"
    STATE_OF_MIND_OWNED = "state_of_mind_owned"
    PARTNER_OWNED_INTERNAL_USE = "partner_owned_internal_use"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"


class PiiStatus(StrEnum):
    NONE_DETECTED = "none_detected"
    POSSIBLE_PII = "possible_pii"
    CONTAINS_PII = "contains_pii"
    REDACTED = "redacted"
    APPROVED_FOR_LIMITED_USE = "approved_for_limited_use"


class CaptureEventType(StrEnum):
    PAGE_LOAD = "page_load"
    CLICK = "click"
    SCROLL = "scroll"
    SCREENSHOT = "screenshot"
    NOTE = "note"
    VIDEO_START = "video_start"
    VIDEO_END = "video_end"
    AUDIO_CHECK = "audio_check"


class ChunkType(StrEnum):
    TRANSCRIPT = "transcript"
    OCR = "ocr"
    SUMMARY = "summary"
    QUIZ = "quiz"
    IMAGE_CAPTION = "image_caption"
    REPORT_ROW = "report_row"
    OPERATOR_NOTE = "operator_note"


class GeneratedTrainingFormat(StrEnum):
    MODULE = "module"
    QUIZ = "quiz"
    FLASHCARDS = "flashcards"
    SOP_CHECKLIST = "sop_checklist"
    ROLEPLAY = "roleplay"
    MANAGER_COACHING_GUIDE = "manager_coaching_guide"


class CaptureBatch(BaseModel):
    capture_batch_id: str = Field(default_factory=lambda: new_id("batch"))
    permission_basis: str = "seedtalent_contract_full_use"
    scope_description: str
    operator: str
    started_at: datetime = Field(default_factory=now_utc)
    completed_at: datetime | None = None
    status: CaptureStatus = CaptureStatus.CREATED
    notes: str | None = None


class CaptureSession(BaseModel):
    capture_session_id: str = Field(default_factory=lambda: new_id("session"))
    capture_batch_id: str
    source_platform: SourcePlatform = SourcePlatform.SEEDTALENT
    capture_mode: CaptureMode = CaptureMode.AUTHORIZED_SCREEN_CAPTURE
    source_url: str | None = None
    course_title: str | None = None
    module_title: str | None = None
    lesson_title: str | None = None
    brand: str | None = None
    jurisdiction: str | None = None
    raw_video_uri: str | None = None
    raw_audio_uri: str | None = None
    screenshot_folder_uri: str | None = None
    browser_profile: str | None = None
    viewport_width: int = 1920
    viewport_height: int = 1080
    started_at: datetime = Field(default_factory=now_utc)
    ended_at: datetime | None = None
    status: CaptureStatus = CaptureStatus.CREATED
    qa_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    permission_basis: str = "seedtalent_contract_full_use"
    notes: str | None = None

    @field_validator("viewport_width", "viewport_height")
    @classmethod
    def viewport_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("viewport dimensions must be positive")
        return value


class CaptureEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("event"))
    capture_session_id: str
    event_type: CaptureEventType
    timestamp_ms: int = Field(ge=0)
    url: str | None = None
    page_title: str | None = None
    visible_label: str | None = None
    operator_note: str | None = None
    screenshot_uri: str | None = None
    created_at: datetime = Field(default_factory=now_utc)

    @model_validator(mode="after")
    def note_events_need_note(self) -> "CaptureEvent":
        if self.event_type == CaptureEventType.NOTE and not self.operator_note:
            raise ValueError("note events require operator_note")
        return self


class VisualFrame(BaseModel):
    frame_id: str = Field(default_factory=lambda: new_id("frame"))
    capture_session_id: str
    timestamp_ms: int = Field(ge=0)
    image_uri: str
    ocr_text: str | None = None
    ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    detected_entities: list[str] = Field(default_factory=list)
    slide_change_score: float | None = Field(default=None, ge=0.0, le=1.0)
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW


class AudioTranscriptSegment(BaseModel):
    segment_id: str = Field(default_factory=lambda: new_id("segment"))
    capture_session_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    speaker: str | None = None
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW

    @model_validator(mode="after")
    def end_after_start(self) -> "AudioTranscriptSegment":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class ReconstructedLesson(BaseModel):
    lesson_id: str = Field(default_factory=lambda: new_id("lesson"))
    capture_session_id: str
    course_title: str | None = None
    module_title: str | None = None
    lesson_title: str
    lesson_order: int | None = Field(default=None, ge=0)
    summary: str | None = None
    learning_objectives: list[str] = Field(default_factory=list)
    source_start_ms: int = Field(ge=0)
    source_end_ms: int = Field(ge=0)
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW

    @model_validator(mode="after")
    def source_end_after_start(self) -> "ReconstructedLesson":
        if self.source_end_ms <= self.source_start_ms:
            raise ValueError("source_end_ms must be greater than source_start_ms")
        return self


class ContentChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: new_id("chunk"))
    capture_session_id: str
    lesson_id: str | None = None
    chunk_type: ChunkType
    text: str
    source_start_ms: int | None = Field(default=None, ge=0)
    source_end_ms: int | None = Field(default=None, ge=0)
    source_screenshot_uri: str | None = None
    source_video_uri: str | None = None
    brand: str | None = None
    jurisdiction: str | None = None
    rights_status: RightsStatus = RightsStatus.UNKNOWN
    pii_status: PiiStatus = PiiStatus.NONE_DETECTED
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    embedding_id: str | None = None

    @model_validator(mode="after")
    def requires_source_citation(self) -> "ContentChunk":
        has_time = self.source_start_ms is not None or self.source_end_ms is not None
        has_media = bool(self.source_screenshot_uri or self.source_video_uri)
        if not (has_time or has_media):
            raise ValueError("content chunks require timestamp and/or media citation")
        if self.source_start_ms is not None and self.source_end_ms is not None:
            if self.source_end_ms <= self.source_start_ms:
                raise ValueError("source_end_ms must be greater than source_start_ms")
        return self

    @property
    def eligible_for_generation(self) -> bool:
        return (
            self.review_status == ReviewStatus.APPROVED
            and self.rights_status not in {RightsStatus.UNKNOWN, RightsStatus.RESTRICTED}
            and self.pii_status in {PiiStatus.NONE_DETECTED, PiiStatus.REDACTED, PiiStatus.APPROVED_FOR_LIMITED_USE}
        )


class CaptureQAReport(BaseModel):
    qa_report_id: str = Field(default_factory=lambda: new_id("qa"))
    capture_session_id: str
    generated_at: datetime = Field(default_factory=now_utc)
    duration_ms: int | None = Field(default=None, ge=0)
    audio_detected: bool | None = None
    screenshot_count: int = Field(default=0, ge=0)
    transcript_segment_count: int = Field(default=0, ge=0)
    visual_frame_count: int = Field(default=0, ge=0)
    low_confidence_transcript_count: int = Field(default=0, ge=0)
    low_confidence_ocr_count: int = Field(default=0, ge=0)
    possible_pii_count: int = Field(default=0, ge=0)
    missing_sections: list[str] = Field(default_factory=list)
    recommended_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    notes: str | None = None


class GeneratedTrainingModule(BaseModel):
    module_id: str = Field(default_factory=lambda: new_id("module"))
    title: str
    target_role: str | None = None
    topic: str
    jurisdiction: str | None = None
    format: GeneratedTrainingFormat
    body_json: dict[str, Any]
    source_chunk_ids: list[str]
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    created_at: datetime = Field(default_factory=now_utc)
    approved_by: str | None = None
    approved_at: datetime | None = None

    @field_validator("source_chunk_ids")
    @classmethod
    def source_chunks_required(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("generated training requires at least one source chunk")
        return value
