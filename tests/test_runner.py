from pathlib import Path

import pytest
from playwright.sync_api import Error, Page, sync_playwright

from som_seedtalent_capture.autopilot.capture_plan import build_fixture_capture_plan_from_file
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
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


class StubMediaController:
    handled_kinds: list[PageKind]

    def __init__(self) -> None:
        self.handled_kinds = []

    def handle(
        self,
        *,
        page: Page,
        observation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> list[RunnerEvent]:
        self.handled_kinds.append(observation.page_kind)
        play_label = "Play Lesson Video" if observation.page_kind == PageKind.LESSON_VIDEO else "Play Lesson Audio"
        page.get_by_role("button", name=play_label).click()
        page.get_by_role("button", name="Next").click()
        page.wait_for_load_state("domcontentloaded")
        return [
            RunnerEvent(
                event_type=RunnerEventType.CLICK,
                timestamp_ms=timestamp_ms,
                execution_url=page.url,
                logical_url=logical_url,
                page_kind=observation.page_kind,
                detail=play_label,
            )
        ]


class StubQuizController:
    handled = False

    def handle(
        self,
        *,
        page: Page,
        observation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> list[RunnerEvent]:
        self.handled = True
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


def test_runner_captures_catalog_and_overview_artifacts(tmp_path: Path):
    _ensure_chromium_or_skip()

    plan = _build_capture_plan()
    result = run_fixture_autopilot(
        plan=plan,
        fixture_root=FIXTURE_ROOT,
        artifact_root=tmp_path,
        start_url_override="https://app.seedtalent.com/catalog.html",
        max_steps=2,
    )

    assert [snapshot.page_kind for snapshot in result.page_snapshots] == [PageKind.CATALOG, PageKind.COURSE_OVERVIEW]
    assert result.decisions[0].page_kind == PageKind.CATALOG
    assert result.decisions[1].page_kind == PageKind.COURSE_OVERVIEW
    assert all(Path(snapshot.screenshot_uri).exists() for snapshot in result.page_snapshots)
    assert "Assigned Learning Catalog" in result.page_snapshots[0].visible_text
    assert "Start Course" in result.page_snapshots[1].buttons


def test_runner_dispatches_media_and_quiz_hooks_to_reach_completion(tmp_path: Path):
    _ensure_chromium_or_skip()

    plan = _build_capture_plan()
    media_controller = StubMediaController()
    quiz_controller = StubQuizController()

    result = run_fixture_autopilot(
        plan=plan,
        fixture_root=FIXTURE_ROOT,
        artifact_root=tmp_path,
        headless=True,
        media_controller=media_controller,
        quiz_controller=quiz_controller,
    )

    assert result.completion_detected is True
    assert media_controller.handled_kinds == [PageKind.LESSON_VIDEO, PageKind.LESSON_AUDIO]
    assert quiz_controller.handled is True
    assert any(event.event_type == RunnerEventType.MEDIA_CONTROLLER_HANDOFF for event in result.events)
    assert any(event.event_type == RunnerEventType.QUIZ_CONTROLLER_HANDOFF for event in result.events)
    assert result.page_snapshots[-1].page_kind == PageKind.COMPLETION_PAGE


def test_runner_marks_unknown_ui_state(tmp_path: Path):
    _ensure_chromium_or_skip()

    unknown_html = tmp_path / "unknown.html"
    unknown_html.write_text(
        """<!DOCTYPE html>
<html lang="en">
  <head><meta charset="utf-8" /><title>Unclassified Fixture</title></head>
  <body>
    <main><p>No known fixture cues are present here.</p></main>
  </body>
</html>
""",
        encoding="utf-8",
    )

    plan = _build_capture_plan()
    result = run_fixture_autopilot(
        plan=plan,
        fixture_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        start_url_override="https://app.seedtalent.com/unknown.html",
        max_steps=1,
    )

    assert result.unknown_ui_state_detected is True
    assert result.stopped_reason == "unknown_ui_state"
    assert result.page_snapshots[0].page_kind == PageKind.UNKNOWN
    assert any(event.event_type == RunnerEventType.UNKNOWN_UI_STATE for event in result.events)
