from pathlib import Path

import pytest
from playwright.sync_api import Error, sync_playwright

from som_seedtalent_capture.autopilot.capture_plan import build_fixture_capture_plan_from_file
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.media_controller import FixtureMediaController
from som_seedtalent_capture.autopilot.qa import AutopilotReadinessStatus, RecaptureReason, evaluate_autopilot_run
from som_seedtalent_capture.autopilot.quiz_controller import FixtureQuizController
from som_seedtalent_capture.autopilot.recorder import FakeRecorderProvider
from som_seedtalent_capture.autopilot.runner import run_fixture_autopilot
from som_seedtalent_capture.permissions import load_permission_manifest


FIXTURE_ROOT = Path("tests/fixtures/fake_seedtalent")
MANIFEST_PATH = Path("config/permission_manifest.example.yaml")


def _ensure_chromium_or_skip() -> None:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Error as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"Playwright Chromium is not installed: {exc}")


def _build_capture_plan():
    discovery = discover_fixture_courses_from_file(
        path=FIXTURE_ROOT / "catalog.html",
        catalog_url="https://app.seedtalent.com/catalog.html",
        screenshot_uri="artifacts/screenshots/catalog.png",
        manifest=load_permission_manifest(MANIFEST_PATH),
    )
    return build_fixture_capture_plan_from_file(
        inventory_item=discovery.items[0],
        path=FIXTURE_ROOT / "lesson-list.html",
        lesson_list_url="https://app.seedtalent.com/lesson-list.html",
    )


@pytest.fixture(scope="module")
def successful_run_bundle(tmp_path_factory):
    _ensure_chromium_or_skip()
    artifact_root = tmp_path_factory.mktemp("qa-fixture-run")
    plan = _build_capture_plan()
    run_result = run_fixture_autopilot(
        plan=plan,
        fixture_root=FIXTURE_ROOT,
        artifact_root=artifact_root,
        headless=True,
        media_controller=FixtureMediaController(mock_completion=True),
        quiz_controller=FixtureQuizController(),
        recorder_provider=FakeRecorderProvider(emit_audio_artifact=True),
    )
    return plan, run_result


def test_evaluate_autopilot_run_ready_for_reconstruction(successful_run_bundle):
    plan, run_result = successful_run_bundle
    qa_result = evaluate_autopilot_run(run_result=run_result, plan=plan)

    assert qa_result.readiness_status == AutopilotReadinessStatus.READY_FOR_RECONSTRUCTION
    assert qa_result.recapture_reasons == []
    assert qa_result.qa_report.screenshot_count >= plan.qa_thresholds.min_screenshot_count


@pytest.mark.parametrize(
    ("reason", "prohibited_path_detected"),
    [
        (RecaptureReason.MISSING_AUDIO, False),
        (RecaptureReason.LOW_SCREENSHOT_COUNT, False),
        (RecaptureReason.COMPLETION_NOT_DETECTED, False),
        (RecaptureReason.LESSON_COUNT_MISMATCH, False),
        (RecaptureReason.UNKNOWN_UI_STATE, False),
        (RecaptureReason.PROHIBITED_PATH_DETECTED, True),
    ],
)
def test_evaluate_autopilot_run_recapture_reasons(successful_run_bundle, reason: RecaptureReason, prohibited_path_detected: bool):
    plan, run_result = successful_run_bundle

    mutated_plan = plan
    mutated_run = run_result

    if reason == RecaptureReason.MISSING_AUDIO:
        mutated_run = run_result.model_copy(
            update={"recorder_session": run_result.recorder_session.model_copy(update={"audio_uri": None})},
            deep=True,
        )
    elif reason == RecaptureReason.LOW_SCREENSHOT_COUNT:
        mutated_plan = plan.model_copy(
            update={"qa_thresholds": plan.qa_thresholds.model_copy(update={"min_screenshot_count": 100})},
            deep=True,
        )
    elif reason == RecaptureReason.COMPLETION_NOT_DETECTED:
        mutated_run = run_result.model_copy(update={"completion_detected": False}, deep=True)
    elif reason == RecaptureReason.LESSON_COUNT_MISMATCH:
        mutated_plan = plan.model_copy(update={"expected_lesson_count": plan.expected_lesson_count + 1}, deep=True)
    elif reason == RecaptureReason.UNKNOWN_UI_STATE:
        mutated_run = run_result.model_copy(update={"unknown_ui_state_detected": True}, deep=True)

    qa_result = evaluate_autopilot_run(
        run_result=mutated_run,
        plan=mutated_plan,
        prohibited_path_detected=prohibited_path_detected,
    )

    assert qa_result.readiness_status == AutopilotReadinessStatus.NEEDS_RECAPTURE
    assert reason in qa_result.recapture_reasons
