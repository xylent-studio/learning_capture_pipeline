from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import CapturePlan
from som_seedtalent_capture.autopilot.runner import AutopilotRunResult
from som_seedtalent_capture.autopilot.state_machine import PageKind
from som_seedtalent_capture.models import CaptureQAReport, ReviewStatus


class RecaptureReason(StrEnum):
    MISSING_AUDIO = "missing_audio"
    LOW_SCREENSHOT_COUNT = "low_screenshot_count"
    COMPLETION_NOT_DETECTED = "completion_not_detected"
    LESSON_COUNT_MISMATCH = "lesson_count_mismatch"
    UNKNOWN_UI_STATE = "unknown_ui_state"
    PROHIBITED_PATH_DETECTED = "prohibited_path_detected"


class AutopilotReadinessStatus(StrEnum):
    READY_FOR_RECONSTRUCTION = "ready_for_reconstruction"
    NEEDS_RECAPTURE = "needs_recapture"


class AutopilotQAResult(BaseModel):
    readiness_status: AutopilotReadinessStatus
    recapture_reasons: list[RecaptureReason] = Field(default_factory=list)
    qa_report: CaptureQAReport


def _unique_screenshot_count(run_result: AutopilotRunResult) -> int:
    screenshot_uris = {snapshot.screenshot_uri for snapshot in run_result.page_snapshots}
    screenshot_uris.update(event.screenshot_uri for event in run_result.events if event.screenshot_uri)
    return len(screenshot_uris)


def _media_pages_encountered(run_result: AutopilotRunResult) -> bool:
    return any(
        observation.page_kind in {PageKind.LESSON_VIDEO, PageKind.LESSON_AUDIO}
        for observation in run_result.observations
    )


def _audio_artifact_detected(run_result: AutopilotRunResult) -> bool | None:
    if run_result.recorder_session is None:
        return None
    if run_result.recorder_session.audio_uri is None:
        return False
    return Path(run_result.recorder_session.audio_uri).exists()


def _visited_planned_lessons(run_result: AutopilotRunResult, plan: CapturePlan) -> int:
    planned_lessons = set(plan.lesson_urls)
    return len(planned_lessons.intersection(run_result.visited_logical_urls))


def evaluate_autopilot_run(
    *,
    run_result: AutopilotRunResult,
    plan: CapturePlan,
    prohibited_path_detected: bool = False,
) -> AutopilotQAResult:
    screenshot_count = _unique_screenshot_count(run_result)
    visited_planned_lessons = _visited_planned_lessons(run_result, plan)
    media_pages_encountered = _media_pages_encountered(run_result)
    audio_detected = _audio_artifact_detected(run_result)

    recapture_reasons: list[RecaptureReason] = []

    if media_pages_encountered and audio_detected is False:
        recapture_reasons.append(RecaptureReason.MISSING_AUDIO)

    if screenshot_count < plan.qa_thresholds.min_screenshot_count:
        recapture_reasons.append(RecaptureReason.LOW_SCREENSHOT_COUNT)

    if not run_result.completion_detected:
        recapture_reasons.append(RecaptureReason.COMPLETION_NOT_DETECTED)

    if plan.expected_lesson_count is not None and visited_planned_lessons != plan.expected_lesson_count:
        recapture_reasons.append(RecaptureReason.LESSON_COUNT_MISMATCH)

    if run_result.unknown_ui_state_detected:
        recapture_reasons.append(RecaptureReason.UNKNOWN_UI_STATE)

    if prohibited_path_detected:
        recapture_reasons.append(RecaptureReason.PROHIBITED_PATH_DETECTED)

    readiness_status = (
        AutopilotReadinessStatus.READY_FOR_RECONSTRUCTION
        if not recapture_reasons
        else AutopilotReadinessStatus.NEEDS_RECAPTURE
    )
    recommended_status = ReviewStatus.NEEDS_REVIEW if not recapture_reasons else ReviewStatus.NEEDS_RECAPTURE

    qa_report = CaptureQAReport(
        capture_session_id=run_result.course_title,
        audio_detected=audio_detected,
        screenshot_count=screenshot_count,
        missing_sections=[reason.value for reason in recapture_reasons],
        recommended_status=recommended_status,
        notes=f"visited_planned_lessons={visited_planned_lessons}",
    )

    return AutopilotQAResult(
        readiness_status=readiness_status,
        recapture_reasons=recapture_reasons,
        qa_report=qa_report,
    )
