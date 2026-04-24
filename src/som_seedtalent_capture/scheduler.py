from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import CapturePlan
from som_seedtalent_capture.autopilot.qa import AutopilotQAResult, AutopilotReadinessStatus


class SchedulerItemStatus(StrEnum):
    QUEUED = "queued"
    PREFLIGHT_FAILED = "preflight_failed"
    BLOCKED_BY_AUTH = "blocked_by_auth"
    READY_FOR_LIVE_CAPTURE = "ready_for_live_capture"
    NEEDS_RECAPTURE = "needs_recapture"
    COMPLETED = "completed"


class SafeRetryCategory(StrEnum):
    UNKNOWN_UI_STATE = "unknown_ui_state"
    MISSING_AUDIO = "missing_audio"
    LOW_SCREENSHOT_COUNT = "low_screenshot_count"


class SchedulerConfig(BaseModel):
    rate_limit_delay_seconds: int = Field(default=5, ge=0)
    max_auth_failures: int = Field(default=2, ge=1)
    max_safe_retries: int = Field(default=1, ge=0)
    safe_retry_categories: list[SafeRetryCategory] = Field(
        default_factory=lambda: [
            SafeRetryCategory.UNKNOWN_UI_STATE,
            SafeRetryCategory.MISSING_AUDIO,
            SafeRetryCategory.LOW_SCREENSHOT_COUNT,
        ]
    )


class ScheduledCourseItem(BaseModel):
    course_title: str
    source_url: str
    status: SchedulerItemStatus = SchedulerItemStatus.QUEUED
    safe_retry_count: int = Field(default=0, ge=0)
    sequence_number: int = Field(default=0, ge=0)


class SchedulerBatchSummary(BaseModel):
    total_courses: int
    queued_count: int = 0
    ready_for_live_capture_count: int = 0
    ready_for_reconstruction_count: int = 0
    needs_recapture_count: int = 0
    blocked_by_auth_count: int = 0
    preflight_failed_count: int = 0
    completed_count: int = 0
    stopped_for_auth_failures: bool = False
    queued_urls: list[str] = Field(default_factory=list)


def build_scheduler_queue(plans: list[CapturePlan], config: SchedulerConfig) -> list[ScheduledCourseItem]:
    del config
    return [
        ScheduledCourseItem(
            course_title=plan.course_title,
            source_url=plan.source_url,
            status=SchedulerItemStatus.QUEUED,
            sequence_number=index,
        )
        for index, plan in enumerate(plans, start=1)
    ]


def mark_queue_ready_for_live_capture(queue: list[ScheduledCourseItem]) -> list[ScheduledCourseItem]:
    return [
        item.model_copy(update={"status": SchedulerItemStatus.READY_FOR_LIVE_CAPTURE})
        for item in queue
    ]


def block_queue_for_auth(queue: list[ScheduledCourseItem]) -> list[ScheduledCourseItem]:
    return [
        item.model_copy(update={"status": SchedulerItemStatus.BLOCKED_BY_AUTH})
        for item in queue
    ]


def should_stop_for_auth_failures(*, failure_reasons: list[str], max_auth_failures: int) -> bool:
    auth_failures = [reason for reason in failure_reasons if reason in {"auth_expired", "failed", "prohibited_path"}]
    return len(auth_failures) >= max_auth_failures


def summarize_scheduler_results(
    *,
    queue: list[ScheduledCourseItem],
    qa_results: list[AutopilotQAResult],
    auth_failure_reasons: list[str],
    config: SchedulerConfig,
) -> SchedulerBatchSummary:
    return SchedulerBatchSummary(
        total_courses=len(queue),
        queued_count=sum(1 for item in queue if item.status == SchedulerItemStatus.QUEUED),
        ready_for_live_capture_count=sum(1 for item in queue if item.status == SchedulerItemStatus.READY_FOR_LIVE_CAPTURE),
        ready_for_reconstruction_count=sum(
            1 for result in qa_results if result.readiness_status == AutopilotReadinessStatus.READY_FOR_RECONSTRUCTION
        ),
        needs_recapture_count=sum(
            1 for result in qa_results if result.readiness_status == AutopilotReadinessStatus.NEEDS_RECAPTURE
        ),
        blocked_by_auth_count=sum(1 for item in queue if item.status == SchedulerItemStatus.BLOCKED_BY_AUTH),
        preflight_failed_count=sum(1 for item in queue if item.status == SchedulerItemStatus.PREFLIGHT_FAILED),
        completed_count=sum(1 for item in queue if item.status == SchedulerItemStatus.COMPLETED),
        stopped_for_auth_failures=should_stop_for_auth_failures(
            failure_reasons=auth_failure_reasons,
            max_auth_failures=config.max_auth_failures,
        ),
        queued_urls=[item.source_url for item in queue],
    )
