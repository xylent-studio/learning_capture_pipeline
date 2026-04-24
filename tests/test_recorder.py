from pathlib import Path

import pytest
from playwright.sync_api import Error, sync_playwright

from som_seedtalent_capture.autopilot.capture_plan import QuizCaptureMode, build_fixture_capture_plan_from_file
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.media_controller import FixtureMediaController
from som_seedtalent_capture.autopilot.quiz_controller import FixtureQuizController
from som_seedtalent_capture.autopilot.recorder import (
    FFmpegRecorderProvider,
    FakeRecorderProvider,
    ObsRecorderProvider,
    RecorderSessionStatus,
    RecorderStartRequest,
)
from som_seedtalent_capture.autopilot.runner import RunnerEventType, run_fixture_autopilot
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


def test_fake_recorder_provider_brackets_runner_execution(tmp_path: Path):
    _ensure_chromium_or_skip()

    plan = _build_capture_plan()
    recorder = FakeRecorderProvider(emit_audio_artifact=True)
    result = run_fixture_autopilot(
        plan=plan,
        fixture_root=FIXTURE_ROOT,
        artifact_root=tmp_path,
        headless=True,
        media_controller=FixtureMediaController(mock_completion=True),
        quiz_controller=FixtureQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT),
        recorder_provider=recorder,
    )

    assert result.completion_detected is True
    assert result.recorder_session is not None
    assert result.recorder_session.status == RecorderSessionStatus.STOPPED
    assert Path(result.recorder_session.video_uri).exists()
    assert Path(result.recorder_session.audio_uri or "").exists()
    assert any(event.event_type == RunnerEventType.RECORDER_START for event in result.events)
    assert any(event.event_type == RunnerEventType.RECORDER_STOP for event in result.events)


def test_ffmpeg_recorder_provider_returns_skeleton_command(tmp_path: Path):
    session = FFmpegRecorderProvider().start(
        RecorderStartRequest(
            artifact_root=str(tmp_path),
            course_title="Retail Safety Basics",
            recorder_profile=_build_capture_plan().recorder_profile,
        )
    )

    assert session.provider_name == "ffmpeg_recorder"
    assert session.planned_command[:4] == ["ffmpeg", "-y", "-f", "gdigrab"]
    assert session.audio_uri is not None


def test_obs_recorder_provider_returns_skeleton_metadata(tmp_path: Path):
    session = ObsRecorderProvider().start(
        RecorderStartRequest(
            artifact_root=str(tmp_path),
            course_title="Retail Safety Basics",
            recorder_profile=_build_capture_plan().recorder_profile,
        )
    )

    assert session.provider_name == "obs_recorder"
    assert session.metadata["mode"] == "skeleton"
    assert session.metadata["scene"] == "SeedTalent Capture"
