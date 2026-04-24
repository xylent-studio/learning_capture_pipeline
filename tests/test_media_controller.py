from pathlib import Path

import pytest
from playwright.sync_api import Error, Page, sync_playwright

from som_seedtalent_capture.autopilot.capture_plan import build_fixture_capture_plan_from_file
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.media_controller import FixtureMediaController, inspect_media_playback_state
from som_seedtalent_capture.autopilot.runner import RunnerEvent, RunnerEventType, run_fixture_autopilot
from som_seedtalent_capture.autopilot.state_machine import PageKind
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


class StubQuizController:
    def handle(
        self,
        *,
        page: Page,
        observation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> list[RunnerEvent]:
        page.locator("input[name='q1']").first.check()
        page.get_by_role("button", name="Submit").click()
        page.wait_for_load_state("domcontentloaded")
        page.get_by_role("button", name="Continue").click()
        page.wait_for_load_state("domcontentloaded")
        return [
            RunnerEvent(
                event_type=RunnerEventType.CLICK,
                timestamp_ms=timestamp_ms,
                execution_url=page.url,
                logical_url=logical_url,
                page_kind=observation.page_kind,
                detail="Submit quiz and continue",
            )
        ]


@pytest.mark.parametrize(
    ("fixture_name", "page_kind", "expected_label"),
    [
        ("lesson-video.html", PageKind.LESSON_VIDEO, "Play Lesson Video"),
        ("lesson-audio.html", PageKind.LESSON_AUDIO, "Play Lesson Audio"),
    ],
)
def test_inspect_media_playback_state_reads_visible_controls(fixture_name: str, page_kind: PageKind, expected_label: str):
    _ensure_chromium_or_skip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto((FIXTURE_ROOT / fixture_name).resolve().as_uri(), wait_until="domcontentloaded")
        state = inspect_media_playback_state(page, page_kind)
        browser.close()

    assert state.media_element_found is True
    assert state.visible_next_enabled is True
    assert state.control_label == expected_label


def test_fixture_media_controller_emits_start_and_end_events(tmp_path: Path):
    _ensure_chromium_or_skip()

    plan = _build_capture_plan()
    result = run_fixture_autopilot(
        plan=plan,
        fixture_root=FIXTURE_ROOT,
        artifact_root=tmp_path,
        headless=True,
        media_controller=FixtureMediaController(mock_completion=True),
        quiz_controller=StubQuizController(),
    )

    media_events = [event.event_type for event in result.events if event.event_type in {RunnerEventType.MEDIA_START, RunnerEventType.MEDIA_END}]

    assert result.completion_detected is True
    assert media_events.count(RunnerEventType.MEDIA_START) == 2
    assert media_events.count(RunnerEventType.MEDIA_END) == 2
