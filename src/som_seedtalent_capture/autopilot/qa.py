from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import CapturePlan
from som_seedtalent_capture.autopilot.runner import AutopilotRunResult
from som_seedtalent_capture.autopilot.state_machine import PageKind
from som_seedtalent_capture.artifacts import ArtifactKind
from som_seedtalent_capture.models import CaptureQAReport, ReviewStatus
from som_seedtalent_capture.pilot_manifests import PilotRunManifest, PilotRunStatus


class RecaptureReason(StrEnum):
    MISSING_AUDIO = "missing_audio"
    LOW_SCREENSHOT_COUNT = "low_screenshot_count"
    COMPLETION_NOT_DETECTED = "completion_not_detected"
    LESSON_COUNT_MISMATCH = "lesson_count_mismatch"
    UNKNOWN_UI_STATE = "unknown_ui_state"
    PROHIBITED_PATH_DETECTED = "prohibited_path_detected"
    PREFLIGHT_FAILED = "preflight_failed"
    MISSING_PAGE_OBSERVATIONS = "missing_page_observations"
    DUPLICATE_SCREENSHOTS = "duplicate_screenshots"
    TOO_SHORT_RUN_DURATION = "too_short_run_duration"
    RUNNER_NOT_EXECUTED = "runner_not_executed"
    MISSING_PLANNED_ARTIFACTS = "missing_planned_artifacts"


class AutopilotReadinessStatus(StrEnum):
    READY_FOR_LIVE_CAPTURE = "ready_for_live_capture"
    READY_FOR_RECONSTRUCTION = "ready_for_reconstruction"
    NEEDS_RECAPTURE = "needs_recapture"


class AutopilotQAResult(BaseModel):
    readiness_status: AutopilotReadinessStatus
    recapture_reasons: list[RecaptureReason] = Field(default_factory=list)
    qa_report: CaptureQAReport
    warnings: list[str] = Field(default_factory=list)


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


def evaluate_pilot_run_manifest(
    *,
    run_manifest: PilotRunManifest,
    minimum_duration_ms: int = 1000,
) -> AutopilotQAResult:
    recapture_reasons: list[RecaptureReason] = []
    warnings: list[str] = []

    artifact_existence = {
        artifact.kind.value: Path(artifact.local_path).exists()
        for artifact in run_manifest.planned_artifacts
        if artifact.kind not in {
            ArtifactKind.SCREEN_RECORDING,
            ArtifactKind.AUDIO_RECORDING,
            ArtifactKind.OCR_OUTPUT,
            ArtifactKind.TRANSCRIPT_OUTPUT,
            ArtifactKind.QA_REPORT,
        }
    }
    missing_planned_artifacts = [kind for kind, exists in artifact_existence.items() if not exists]

    screenshot_count = len(run_manifest.screenshot_uris)
    duplicate_screenshots = screenshot_count != len(set(run_manifest.screenshot_uris))

    if run_manifest.preflight_status in {"failed", "auth_expired", "prohibited_path"} or run_manifest.lifecycle_status in {
        PilotRunStatus.PREFLIGHT_FAILED,
        PilotRunStatus.BLOCKED_BY_AUTH,
    }:
        recapture_reasons.append(RecaptureReason.PREFLIGHT_FAILED)

    if run_manifest.page_observation_count == 0 and run_manifest.runner_executed:
        recapture_reasons.append(RecaptureReason.MISSING_PAGE_OBSERVATIONS)

    if duplicate_screenshots:
        recapture_reasons.append(RecaptureReason.DUPLICATE_SCREENSHOTS)

    if run_manifest.duration_ms is not None and 0 < run_manifest.duration_ms < minimum_duration_ms:
        recapture_reasons.append(RecaptureReason.TOO_SHORT_RUN_DURATION)

    if run_manifest.diagnostics_snapshot and run_manifest.diagnostics_snapshot.prohibited_path_detected:
        recapture_reasons.append(RecaptureReason.PROHIBITED_PATH_DETECTED)

    if missing_planned_artifacts:
        recapture_reasons.append(RecaptureReason.MISSING_PLANNED_ARTIFACTS)

    if not run_manifest.runner_executed and run_manifest.lifecycle_status == PilotRunStatus.READY_FOR_LIVE_CAPTURE:
        warnings.append(RecaptureReason.RUNNER_NOT_EXECUTED.value)

    if recapture_reasons:
        readiness_status = AutopilotReadinessStatus.NEEDS_RECAPTURE
        recommended_status = ReviewStatus.NEEDS_RECAPTURE
    elif run_manifest.lifecycle_status == PilotRunStatus.READY_FOR_LIVE_CAPTURE:
        readiness_status = AutopilotReadinessStatus.READY_FOR_LIVE_CAPTURE
        recommended_status = ReviewStatus.NEEDS_REVIEW
    else:
        readiness_status = AutopilotReadinessStatus.READY_FOR_RECONSTRUCTION
        recommended_status = ReviewStatus.NEEDS_REVIEW

    qa_report = CaptureQAReport(
        capture_session_id=run_manifest.capture_session_id,
        duration_ms=run_manifest.duration_ms,
        screenshot_count=screenshot_count,
        low_confidence_ocr_count=0,
        low_confidence_transcript_count=0,
        missing_sections=[reason.value for reason in recapture_reasons] + warnings,
        recommended_status=recommended_status,
        notes=f"lifecycle_status={run_manifest.lifecycle_status.value}",
    )

    return AutopilotQAResult(
        readiness_status=readiness_status,
        recapture_reasons=recapture_reasons,
        qa_report=qa_report,
        warnings=warnings,
    )
