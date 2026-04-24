from pathlib import Path

import pytest

from som_seedtalent_capture.autopilot.capture_plan import (
    QuizCaptureMode,
    RecorderProfile,
    build_fixture_capture_plan,
    build_fixture_capture_plan_from_file,
)
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.state_machine import PageKind
from som_seedtalent_capture.permissions import load_permission_manifest


FIXTURE_ROOT = Path("tests/fixtures/fake_seedtalent")
MANIFEST_PATH = Path("config/permission_manifest.example.yaml")


def _discovered_inventory_item():
    discovery = discover_fixture_courses_from_file(
        path=FIXTURE_ROOT / "catalog.html",
        catalog_url="https://app.seedtalent.com/catalog.html",
        screenshot_uri="artifacts/screenshots/catalog.png",
        manifest=load_permission_manifest(MANIFEST_PATH),
    )
    return discovery.items[0]


def test_build_fixture_capture_plan_from_lesson_list():
    plan = build_fixture_capture_plan_from_file(
        inventory_item=_discovered_inventory_item(),
        path=FIXTURE_ROOT / "lesson-list.html",
        lesson_list_url="https://app.seedtalent.com/lesson-list.html",
    )

    assert plan.course_title == "Retail Safety Basics"
    assert plan.permission_basis == "seedtalent_contract_full_use"
    assert plan.recorder_profile == RecorderProfile.FIXTURE_NOOP
    assert plan.quiz_mode == QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT
    assert plan.max_course_duration_minutes == 30
    assert plan.screenshot_interval_seconds == 20
    assert plan.expected_lesson_count == 5
    assert len(plan.lesson_urls) == 5
    assert plan.lesson_list_observation is not None
    assert plan.lesson_list_observation.page_kind == PageKind.LESSON_LIST
    assert plan.qa_thresholds.min_page_observations == 5
    assert plan.qa_thresholds.min_screenshot_count == 5


def test_build_fixture_capture_plan_without_visible_lesson_list():
    plan = build_fixture_capture_plan(
        inventory_item=_discovered_inventory_item(),
        screenshot_interval_seconds=15,
        recorder_profile=RecorderProfile.HEADED_BROWSER_FFMPEG,
        quiz_mode=QuizCaptureMode.CAPTURE_ONLY,
        max_course_duration_minutes=45,
    )

    assert plan.expected_lesson_count is None
    assert plan.lesson_urls == []
    assert plan.lesson_list_observation is None
    assert plan.screenshot_interval_seconds == 15
    assert plan.recorder_profile == RecorderProfile.HEADED_BROWSER_FFMPEG
    assert plan.quiz_mode == QuizCaptureMode.CAPTURE_ONLY
    assert plan.max_course_duration_minutes == 45
    assert plan.qa_thresholds.min_page_observations == 1


def test_build_fixture_capture_plan_rejects_non_lesson_list_input():
    with pytest.raises(ValueError, match="capture plan lesson list input must classify as lesson_list"):
        build_fixture_capture_plan(
            inventory_item=_discovered_inventory_item(),
            lesson_list_html_text=(FIXTURE_ROOT / "course-overview.html").read_text(encoding="utf-8"),
            lesson_list_url="https://app.seedtalent.com/course-overview.html",
        )
