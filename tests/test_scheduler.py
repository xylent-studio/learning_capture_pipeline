from som_seedtalent_capture.autopilot.capture_plan import CapturePlan, QaThresholds, QuizCaptureMode, RecorderProfile
from som_seedtalent_capture.autopilot.qa import AutopilotQAResult, AutopilotReadinessStatus
from som_seedtalent_capture.models import CaptureQAReport, RightsStatus
from som_seedtalent_capture.scheduler import SchedulerConfig, build_scheduler_queue, should_stop_for_auth_failures, summarize_scheduler_results


def _plan(course_title: str) -> CapturePlan:
    return CapturePlan(
        course_title=course_title,
        source_url=f"https://app.seedtalent.com/courses/{course_title.lower().replace(' ', '-')}",
        permission_basis="seedtalent_contract_full_use",
        rights_status=RightsStatus.SEEDTALENT_CONTRACT_FULL_USE,
        screenshot_interval_seconds=5,
        recorder_profile=RecorderProfile.HEADED_BROWSER_FFMPEG,
        quiz_mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT,
        max_course_duration_minutes=30,
        qa_thresholds=QaThresholds(),
    )


def test_scheduler_queue_and_summary():
    plans = [_plan("Course One"), _plan("Course Two")]
    queue = build_scheduler_queue(plans, SchedulerConfig())
    summary = summarize_scheduler_results(
        queue=queue,
        qa_results=[
            AutopilotQAResult(
                readiness_status=AutopilotReadinessStatus.READY_FOR_RECONSTRUCTION,
                qa_report=CaptureQAReport(capture_session_id="session-1"),
            ),
            AutopilotQAResult(
                readiness_status=AutopilotReadinessStatus.NEEDS_RECAPTURE,
                qa_report=CaptureQAReport(capture_session_id="session-2"),
            ),
        ],
        auth_failure_reasons=["auth_expired", "auth_expired"],
        config=SchedulerConfig(max_auth_failures=2),
    )

    assert len(queue) == 2
    assert summary.total_courses == 2
    assert summary.ready_for_reconstruction_count == 1
    assert summary.needs_recapture_count == 1
    assert summary.stopped_for_auth_failures is True


def test_should_stop_for_auth_failures_ignores_non_auth_reasons():
    assert should_stop_for_auth_failures(
        failure_reasons=["unknown_ui_state", "missing_audio"],
        max_auth_failures=1,
    ) is False
