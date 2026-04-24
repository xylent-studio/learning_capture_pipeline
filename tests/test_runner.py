from pathlib import Path

import pytest
from playwright.sync_api import Error, Page, sync_playwright

from som_seedtalent_capture.autopilot.capture_plan import build_fixture_capture_plan_from_file
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.runner import (
    _apply_live_navigation,
    RunnerEvent,
    RunnerEventType,
    _wait_for_live_page_ready,
    run_visible_session_autopilot,
    run_fixture_autopilot,
)
from som_seedtalent_capture.autopilot.state_machine import PageKind
from som_seedtalent_capture.pilot_manifests import FailureCategory
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


def test_wait_for_live_page_ready_polls_until_visible_content() -> None:
    observed_timeouts: list[int] = []

    class _FakeLocator:
        def __init__(self, values: list[str] | None = None, body_text: str | None = None) -> None:
            self._values = values or []
            self._body_text = body_text or ""

        def inner_text(self) -> str:
            return self._body_text

        def all_inner_texts(self) -> list[str]:
            return self._values

    class _FakePage:
        def __init__(self) -> None:
            self.url = "https://app.seedtalent.com/course/example"
            self.body_text = "Loading"
            self.heading_values: list[str] = []
            self.button_values: list[str] = []
            self.link_values: list[str] = []

        def locator(self, selector: str):
            if selector == "body":
                return _FakeLocator(body_text=self.body_text)
            if selector == "h1:visible, h2:visible, h3:visible":
                return _FakeLocator(values=self.heading_values)
            if selector == "button:visible":
                return _FakeLocator(values=self.button_values)
            if selector == "a:visible":
                return _FakeLocator(values=self.link_values)
            raise AssertionError(f"Unexpected selector: {selector}")

        def evaluate(self, script: str):
            del script
            return {
                "dataPageKind": None,
                "count": 0,
                "durationSeconds": None,
                "currentTimeSeconds": None,
                "paused": None,
            }

        def title(self) -> str:
            return "Seed Talent"

        def wait_for_timeout(self, timeout_ms: int) -> None:
            observed_timeouts.append(timeout_ms)
            self.body_text = "Seed & Strain | NY Start Course Continue"
            self.button_values = ["Continue"]

    page = _FakePage()

    _wait_for_live_page_ready(page, timeout_ms=1500)

    assert observed_timeouts == [500]


class _FakeFirstLocator:
    def __init__(self, label: str | None) -> None:
        self._label = label

    @property
    def first(self):
        return self

    def count(self) -> int:
        return 1 if self._label is not None else 0

    def inner_text(self) -> str:
        return self._label or ""

    def click(self) -> None:
        return None

    def filter(self, has_text):  # noqa: ANN001
        del has_text
        return self


class _FakeLiveSurface:
    def __init__(self, button_labels: list[str]) -> None:
        self.button_labels = button_labels

    def get_by_role(self, role: str, name):  # noqa: ANN001
        if role not in {"button", "link"}:
            return _FakeFirstLocator(None)
        for label in self.button_labels:
            if name.search(label):
                return _FakeFirstLocator(label)
        return _FakeFirstLocator(None)

    def locator(self, selector: str):
        if selector == "input[type='checkbox']:visible":
            return _FakeFirstLocator(None)
        if selector in {"button:visible", "a:visible"}:
            return _FakeLiveSurface(self.button_labels)
        return _FakeFirstLocator(None)

    def filter(self, has_text):  # noqa: ANN001
        for label in self.button_labels:
            if has_text.search(label):
                return _FakeFirstLocator(label)
        return _FakeFirstLocator(None)


class _FakeLivePage:
    def __init__(self) -> None:
        self.url = "https://app.seedtalent.com/courses/pilot"

    def goto(self, url: str, wait_until: str | None = None) -> None:
        del wait_until
        self.url = url

    def wait_for_load_state(self, state: str, timeout: int = 5000) -> None:
        del state, timeout

    def wait_for_timeout(self, timeout_ms: int) -> None:
        del timeout_ms


def test_apply_live_navigation_prefers_next_over_take_again_and_skip() -> None:
    plan = _build_capture_plan()
    from som_seedtalent_capture.autopilot.runner import AutopilotRunResult
    from som_seedtalent_capture.autopilot.state_machine import PageObservation

    result = AutopilotRunResult(
        course_title=plan.course_title,
        planned_source_url=plan.source_url,
        artifact_root=str(Path.cwd()),
    )
    live_page = _FakeLivePage()
    surface = _FakeLiveSurface(["SKIP TO LESSON", "NEXT", "TAKE AGAIN"])
    observation = PageObservation(
        url="https://cdn.example/scormcontent/index.html#/quiz/example",
        title="Seed Talent",
        page_kind=PageKind.QUIZ_RESULTS,
        visible_text_sample="Quiz Results",
        buttons=["SKIP TO LESSON", "NEXT", "TAKE AGAIN"],
        links=[],
        confidence=0.95,
    )

    clicked = _apply_live_navigation(
        page=live_page,
        surface=surface,
        observation=observation,
        plan=plan,
        result=result,
    )

    assert clicked == "NEXT"


def test_run_visible_session_autopilot_detects_repeated_same_state(monkeypatch, tmp_path: Path) -> None:
    class _FakeContext:
        def new_page(self):
            return _FakeLivePage()

    class _FakeBrowser:
        def new_context(self, storage_state: str):
            del storage_state
            return _FakeContext()

        def close(self) -> None:
            return None

    class _FakeChromium:
        def launch(self, headless: bool = True):
            del headless
            return _FakeBrowser()

    class _FakePlaywright:
        chromium = _FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    plan = _build_capture_plan().model_copy(update={"lesson_urls": []}, deep=True)
    storage_state_path = tmp_path / "storage-state.json"
    storage_state_path.write_text('{"cookies":[]}', encoding="utf-8")

    snapshot_counter = {"count": 0}

    def _fake_capture_page(**kwargs):  # noqa: ANN003
        del kwargs
        snapshot_counter["count"] += 1
        from som_seedtalent_capture.autopilot.runner import RunnerPageSnapshot
        from som_seedtalent_capture.autopilot.state_machine import PageObservation

        snapshot = RunnerPageSnapshot(
            execution_url="https://cdn.example/scormcontent/index.html#/quiz/example",
            logical_url="https://app.seedtalent.com/courses/pilot-course",
            outer_page_url="https://app.seedtalent.com/courses/pilot-course",
            outer_page_title="Seed Talent",
            active_capture_surface_type="frame",
            active_capture_surface_name="scormdriver_content",
            active_capture_surface_url="https://cdn.example/scormcontent/index.html#/quiz/example",
            title="Seed Talent",
            visible_text="Quiz Results You scored 50% and did not pass. Next Take Again",
            headings=["Quiz Results"],
            buttons=["NEXT", "TAKE AGAIN"],
            links=[],
            screenshot_uri=str(tmp_path / f"step-{snapshot_counter['count']:03d}.png"),
            page_kind=PageKind.QUIZ_RESULTS,
            confidence=0.95,
        )
        observation = PageObservation(
            url=snapshot.execution_url,
            title=snapshot.title,
            page_kind=PageKind.QUIZ_RESULTS,
            visible_text_sample=snapshot.visible_text,
            buttons=snapshot.buttons,
            links=[],
            screenshot_uri=snapshot.screenshot_uri,
            confidence=0.95,
        )
        return snapshot, observation

    monkeypatch.setattr("som_seedtalent_capture.autopilot.runner.sync_playwright", lambda: _FakePlaywright())
    monkeypatch.setattr("som_seedtalent_capture.autopilot.runner._wait_for_live_page_ready", lambda page: page)
    monkeypatch.setattr("som_seedtalent_capture.autopilot.runner._capture_page", _fake_capture_page)
    monkeypatch.setattr("som_seedtalent_capture.autopilot.runner._apply_live_navigation", lambda **kwargs: "NEXT")

    result = run_visible_session_autopilot(
        plan=plan,
        artifact_root=tmp_path,
        storage_state_path=storage_state_path,
        headless=True,
        max_steps=6,
    )

    assert result.failure_category == FailureCategory.REPEATED_SAME_STATE
    assert result.stopped_reason == "repeated_same_state"
    assert result.active_capture_surface == "frame:scormdriver_content"
