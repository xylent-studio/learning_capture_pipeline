from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import CapturePlan
from som_seedtalent_capture.autopilot.qa import AutopilotQAResult, AutopilotReadinessStatus


class SchedulerItemStatus(StrEnum):
    QUEUED = "queued"
    READY_FOR_RUN = "ready_for_run"
    NEEDS_RECAPTURE = "needs_recapture"


class SchedulerConfig(BaseModel):
    rate_limit_delay_seconds: int = Field(default=5, ge=0)
    max_auth_failures: int = Field(default=2, ge=1)
    max_safe_retries: int = Field(default=1, ge=0)


class ScheduledCourseItem(BaseModel):
    course_title: str
    source_url: str
    status: SchedulerItemStatus = SchedulerItemStatus.QUEUED
    safe_retry_count: int = Field(default=0, ge=0)


class SchedulerBatchSummary(BaseModel):
    total_courses: int
    ready_for_reconstruction_count: int = 0
    needs_recapture_count: int = 0
    stopped_for_auth_failures: bool = False
    queued_urls: list[str] = Field(default_factory=list)


def build_scheduler_queue(plans: list[CapturePlan], config: SchedulerConfig) -> list[ScheduledCourseItem]:
    del config
    return [
        ScheduledCourseItem(
            course_title=plan.course_title,
            source_url=plan.source_url,
            status=SchedulerItemStatus.READY_FOR_RUN,
        )
        for plan in plans
    ]


def should_stop_for_auth_failures(*, failure_reasons: list[str], max_auth_failures: int) -> bool:
    auth_failures = [reason for reason in failure_reasons if reason == "auth_expired"]
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
        ready_for_reconstruction_count=sum(
            1 for result in qa_results if result.readiness_status == AutopilotReadinessStatus.READY_FOR_RECONSTRUCTION
        ),
        needs_recapture_count=sum(
            1 for result in qa_results if result.readiness_status == AutopilotReadinessStatus.NEEDS_RECAPTURE
        ),
        stopped_for_auth_failures=should_stop_for_auth_failures(
            failure_reasons=auth_failure_reasons,
            max_auth_failures=config.max_auth_failures,
        ),
        queued_urls=[item.source_url for item in queue],
    )
