from pathlib import Path

import pytest
from playwright.sync_api import Error, sync_playwright

from som_seedtalent_capture.autopilot.capture_plan import QuizCaptureMode, build_fixture_capture_plan_from_file
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.media_controller import FixtureMediaController
from som_seedtalent_capture.autopilot.quiz_controller import FixtureQuizController
from som_seedtalent_capture.autopilot.runner import run_fixture_autopilot
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
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


def test_quiz_controller_capture_only_stays_on_question_page(tmp_path: Path):
    _ensure_chromium_or_skip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto((FIXTURE_ROOT / "quiz.html").resolve().as_uri(), wait_until="domcontentloaded")

        controller = FixtureQuizController(mode=QuizCaptureMode.CAPTURE_ONLY)
        result = controller.run(
            page=page,
            observation=PageObservation(url=page.url, page_kind=PageKind.QUIZ_QUESTION),
            screenshot_dir=tmp_path,
            logical_url="https://app.seedtalent.com/quiz.html",
            timestamp_ms=123,
        )
        browser.close()

    assert result.question_text == "Which action should happen before opening the floor?"
    assert len(result.options) == 3
    assert result.feedback_text is None
    assert result.advanced_to_next is False
    assert Path(result.question_screenshot_uri).exists()


def test_quiz_controller_capture_and_complete_records_feedback(tmp_path: Path):
    _ensure_chromium_or_skip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto((FIXTURE_ROOT / "quiz.html").resolve().as_uri(), wait_until="domcontentloaded")

        controller = FixtureQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)
        result = controller.run(
            page=page,
            observation=PageObservation(url=page.url, page_kind=PageKind.QUIZ_QUESTION),
            screenshot_dir=tmp_path,
            logical_url="https://app.seedtalent.com/quiz.html",
            timestamp_ms=456,
        )
        browser.close()

    assert result.selected_answer == "Confirm the counter area is clear"
    assert "Correct" in (result.feedback_text or "")
    assert result.advanced_to_next is True
    assert result.attempts_used == 1
    assert Path(result.question_screenshot_uri).exists()
    assert Path(result.feedback_screenshot_uri or "").exists()


def test_quiz_controller_model_assisted_stub_stops_cleanly(tmp_path: Path):
    _ensure_chromium_or_skip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto((FIXTURE_ROOT / "quiz.html").resolve().as_uri(), wait_until="domcontentloaded")

        controller = FixtureQuizController(mode=QuizCaptureMode.MODEL_ASSISTED_ANSWER)
        result = controller.run(
            page=page,
            observation=PageObservation(url=page.url, page_kind=PageKind.QUIZ_QUESTION),
            screenshot_dir=tmp_path,
            logical_url="https://app.seedtalent.com/quiz.html",
            timestamp_ms=789,
        )
        browser.close()

    assert result.advanced_to_next is False
    assert result.stopped_reason == "model_assisted_answer_not_implemented"
    assert result.feedback_text is None


def test_runner_reaches_completion_with_real_quiz_controller(tmp_path: Path):
    _ensure_chromium_or_skip()

    plan = _build_capture_plan()
    quiz_controller = FixtureQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)

    result = run_fixture_autopilot(
        plan=plan,
        fixture_root=FIXTURE_ROOT,
        artifact_root=tmp_path,
        headless=True,
        media_controller=FixtureMediaController(mock_completion=True),
        quiz_controller=quiz_controller,
    )

    assert result.completion_detected is True
    assert quiz_controller.last_result is not None
    assert quiz_controller.last_result.feedback_text is not None
    assert quiz_controller.last_result.advanced_to_next is True
