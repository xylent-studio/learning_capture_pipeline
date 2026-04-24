from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol
from urllib.parse import urlparse

from playwright.sync_api import Error, Page, sync_playwright
from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import CapturePlan
from som_seedtalent_capture.autopilot.page_classifier import VisibleDomSnapshot, classify_fixture_page, classify_visible_page
from som_seedtalent_capture.autopilot.recorder import RecorderProvider, RecorderSession, RecorderStartRequest
from som_seedtalent_capture.autopilot.state_machine import CaptureDecision, NavigationAction, PageKind, PageObservation, decide_next_action
from som_seedtalent_capture.pilot_manifests import FailureCategory

_LIVE_PAGE_WAIT_TIMEOUT_MS = 15000
_LIVE_PAGE_WAIT_POLL_MS = 500
_REPEATED_STATE_THRESHOLD = 3
_LOADING_TOKENS = (
    "loading",
    "please wait",
    "just a moment",
    "fetching",
    "preparing",
)
_APP_SHELL_TOKENS = (
    "dashboard",
    "course library",
    "reports",
    "logout",
)


class RunnerEventType(StrEnum):
    RUN_STARTED = "run_started"
    PAGE_LOAD = "page_load"
    SCREENSHOT_CAPTURED = "screenshot_captured"
    DECISION_MADE = "decision_made"
    CLICK = "click"
    RECORDER_START = "recorder_start"
    RECORDER_STOP = "recorder_stop"
    MEDIA_CONTROLLER_HANDOFF = "media_controller_handoff"
    MEDIA_START = "media_start"
    MEDIA_END = "media_end"
    QUIZ_CONTROLLER_HANDOFF = "quiz_controller_handoff"
    UNKNOWN_UI_STATE = "unknown_ui_state"
    RUN_COMPLETED = "run_completed"
    RUN_STOPPED = "run_stopped"


class RunnerEvent(BaseModel):
    event_type: RunnerEventType
    timestamp_ms: int = Field(ge=0)
    execution_url: str | None = None
    logical_url: str | None = None
    page_kind: PageKind | None = None
    detail: str | None = None
    screenshot_uri: str | None = None


class RunnerPageSnapshot(BaseModel):
    execution_url: str
    logical_url: str | None = None
    outer_page_url: str | None = None
    outer_page_title: str | None = None
    active_capture_surface_type: str | None = None
    active_capture_surface_name: str | None = None
    active_capture_surface_url: str | None = None
    title: str | None = None
    visible_text: str = ""
    headings: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    screenshot_uri: str
    page_kind: PageKind = PageKind.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RunnerDecisionRecord(BaseModel):
    execution_url: str
    logical_url: str | None = None
    page_kind: PageKind
    action: NavigationAction
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human: bool = False


class AutopilotRunResult(BaseModel):
    course_title: str
    planned_source_url: str
    artifact_root: str
    recorder_session: RecorderSession | None = None
    page_snapshots: list[RunnerPageSnapshot] = Field(default_factory=list)
    observations: list[PageObservation] = Field(default_factory=list)
    decisions: list[RunnerDecisionRecord] = Field(default_factory=list)
    events: list[RunnerEvent] = Field(default_factory=list)
    visited_execution_urls: list[str] = Field(default_factory=list)
    visited_logical_urls: list[str] = Field(default_factory=list)
    completion_detected: bool = False
    unknown_ui_state_detected: bool = False
    stopped_reason: str | None = None
    failure_category: FailureCategory | None = None
    active_capture_surface: str | None = None


class FixtureMediaController(Protocol):
    def handle(
        self,
        *,
        page: Page,
        observation: PageObservation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> list[RunnerEvent]:
        ...


class FixtureQuizController(Protocol):
    def handle(
        self,
        *,
        page: Page,
        observation: PageObservation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> list[RunnerEvent]:
        ...


def _timestamp_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _basename_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or url
    return Path(path).name


def _resolve_execution_url(logical_url: str, fixture_root: Path) -> str:
    parsed = urlparse(logical_url)
    if parsed.scheme == "file":
        return logical_url
    return (fixture_root / _basename_from_url(logical_url)).resolve().as_uri()


def _build_logical_url_map(plan: CapturePlan, start_url_override: str | None = None) -> dict[str, str]:
    logical_urls = [plan.source_url]
    if plan.lesson_list_url:
        logical_urls.append(plan.lesson_list_url)
    logical_urls.extend(plan.lesson_urls)
    if start_url_override:
        logical_urls.append(start_url_override)
    return {_basename_from_url(url): url for url in logical_urls}


def _extract_visible_snapshot(surface: Any) -> VisibleDomSnapshot:
    visible_text = surface.locator("body").inner_text()
    headings = [text.strip() for text in surface.locator("h1:visible, h2:visible, h3:visible").all_inner_texts() if text.strip()]
    buttons = [text.strip() for text in surface.locator("button:visible").all_inner_texts() if text.strip()]
    links = [text.strip() for text in surface.locator("a:visible").all_inner_texts() if text.strip()]
    media_state = surface.evaluate(
        """() => {
            const media = document.querySelector('video, audio');
            return {
              title: document.title || null,
              dataPageKind: document.body?.dataset?.pageKind ?? null,
              count: document.querySelectorAll('video, audio').length,
              progressbarCount: document.querySelectorAll('[role="progressbar"]').length,
              durationSeconds: media && Number.isFinite(media.duration) ? media.duration : null,
              currentTimeSeconds: media && Number.isFinite(media.currentTime) ? media.currentTime : null,
              paused: media ? media.paused : null,
            };
        }"""
    )

    return VisibleDomSnapshot(
        title=media_state.get("title"),
        data_page_kind=media_state.get("dataPageKind"),
        visible_text=visible_text,
        headings=headings,
        buttons=buttons,
        links=links,
        media={
            "count": media_state.get("count", 0),
            "duration_seconds": media_state.get("durationSeconds"),
            "current_time_seconds": media_state.get("currentTimeSeconds"),
            "paused": media_state.get("paused"),
        },
    )


def _extract_visible_snapshot_with_retry(surface: Any, *, page: Page, retries: int = 3) -> VisibleDomSnapshot:
    for attempt in range(retries):
        try:
            return _extract_visible_snapshot(surface)
        except Error as exc:
            if "Execution context was destroyed" not in str(exc) and "Frame was detached" not in str(exc):
                raise
            if attempt == retries - 1:
                raise
            page.wait_for_timeout(_LIVE_PAGE_WAIT_POLL_MS)
    return _extract_visible_snapshot(surface)


def _snapshot_has_meaningful_content(snapshot: VisibleDomSnapshot) -> bool:
    haystack = " ".join(
        [
            snapshot.title or "",
            snapshot.visible_text,
            " ".join(snapshot.headings),
            " ".join(snapshot.buttons),
            " ".join(snapshot.links),
        ]
    ).strip()
    haystack_lower = haystack.lower()

    if snapshot.headings or snapshot.buttons or snapshot.links or snapshot.media.count > 0:
        return True

    if len(haystack) < 24:
        return False

    return not any(token in haystack_lower for token in _LOADING_TOKENS)


def _snapshot_looks_like_app_shell(snapshot: VisibleDomSnapshot) -> bool:
    haystack_lower = " ".join(
        [
            snapshot.title or "",
            snapshot.visible_text,
            " ".join(snapshot.headings),
            " ".join(snapshot.buttons),
            " ".join(snapshot.links),
        ]
    ).lower()
    return all(token in haystack_lower for token in _APP_SHELL_TOKENS)


def _select_live_capture_surface(page: Page) -> Any:
    preferred_frames = []
    for frame in getattr(page, "frames", []):
        frame_url = getattr(frame, "url", "") or ""
        frame_name = getattr(frame, "name", "") or ""
        if "scormcontent" in frame_url or frame_name == "scormdriver_content":
            preferred_frames.append(frame)

    if preferred_frames:
        return preferred_frames[0]
    return page


def _surface_metadata(page: Page, surface: Any) -> tuple[str, str | None, str | None]:
    if surface is page:
        return "page", None, page.url
    surface_name = getattr(surface, "name", None)
    surface_url = getattr(surface, "url", None)
    return "frame", surface_name or None, surface_url or None


def _wait_for_live_page_ready(page: Page, *, timeout_ms: int = _LIVE_PAGE_WAIT_TIMEOUT_MS) -> Any:
    elapsed_ms = 0
    while elapsed_ms < timeout_ms:
        surface = _select_live_capture_surface(page)
        try:
            snapshot = _extract_visible_snapshot_with_retry(surface, page=page)
        except Error:
            page.wait_for_timeout(_LIVE_PAGE_WAIT_POLL_MS)
            elapsed_ms += _LIVE_PAGE_WAIT_POLL_MS
            continue
        if surface is not page:
            if _snapshot_has_meaningful_content(snapshot):
                return surface
        elif _snapshot_has_meaningful_content(snapshot) and not _snapshot_looks_like_app_shell(snapshot):
            return surface
        page.wait_for_timeout(_LIVE_PAGE_WAIT_POLL_MS)
        elapsed_ms += _LIVE_PAGE_WAIT_POLL_MS
    return _select_live_capture_surface(page)


def _capture_page(
    *,
    page: Page,
    step_index: int,
    screenshot_dir: Path,
    logical_url: str | None,
    classifier=classify_fixture_page,
    capture_surface: Any | None = None,
) -> tuple[RunnerPageSnapshot, PageObservation]:
    screenshot_uri = str((screenshot_dir / f"step-{step_index:03d}.png").resolve())
    page.screenshot(path=screenshot_uri, full_page=True)
    observed_surface = capture_surface or page
    snapshot = _extract_visible_snapshot_with_retry(observed_surface, page=page)
    observed_url = getattr(observed_surface, "url", page.url)
    observation = classifier(url=observed_url, snapshot=snapshot, screenshot_uri=screenshot_uri)
    capture_surface_type, capture_surface_name, capture_surface_url = _surface_metadata(page, observed_surface)
    runner_snapshot = RunnerPageSnapshot(
        execution_url=observed_url,
        logical_url=logical_url,
        outer_page_url=page.url,
        outer_page_title=page.title(),
        active_capture_surface_type=capture_surface_type,
        active_capture_surface_name=capture_surface_name,
        active_capture_surface_url=capture_surface_url,
        title=snapshot.title,
        visible_text=snapshot.visible_text,
        headings=snapshot.headings,
        buttons=snapshot.buttons,
        links=snapshot.links,
        screenshot_uri=screenshot_uri,
        page_kind=observation.page_kind,
        confidence=observation.confidence,
    )
    return runner_snapshot, observation


def _record_page_visit(result: AutopilotRunResult, execution_url: str, logical_url: str | None) -> None:
    if execution_url not in result.visited_execution_urls:
        result.visited_execution_urls.append(execution_url)
    if logical_url and logical_url not in result.visited_logical_urls:
        result.visited_logical_urls.append(logical_url)


def _state_signature(snapshot: RunnerPageSnapshot, observation: PageObservation) -> str:
    visible_text = " ".join(snapshot.visible_text.lower().split())
    return "|".join(
        [
            observation.page_kind.value,
            visible_text[:200],
            ",".join(button.lower() for button in snapshot.buttons[:8]),
            ",".join(link.lower() for link in snapshot.links[:8]),
        ]
    )


def _record_decision(result: AutopilotRunResult, observation: PageObservation, decision: CaptureDecision, logical_url: str | None) -> None:
    result.decisions.append(
        RunnerDecisionRecord(
            execution_url=observation.url,
            logical_url=logical_url,
            page_kind=observation.page_kind,
            action=decision.action,
            reason=decision.reason,
            confidence=decision.confidence,
            requires_human=decision.requires_human,
        )
    )


def _find_next_lesson_basename(plan: CapturePlan, result: AutopilotRunResult) -> str | None:
    for lesson_url in plan.lesson_urls:
        if lesson_url not in result.visited_logical_urls:
            return _basename_from_url(lesson_url)
    return None


def _click_and_wait(page: Page, locator, timeout_ms: int = 5000) -> str:
    label = locator.inner_text().strip()
    locator.click()
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        page.wait_for_timeout(min(timeout_ms, 1000))
    else:
        page.wait_for_timeout(1000)
    return label


def _click_candidate(surface: Any, page: Page, labels: list[str], timeout_ms: int = 5000) -> str | None:
    for label in labels:
        pattern = re.compile(label, re.IGNORECASE)
        button = surface.get_by_role("button", name=pattern).first
        if button.count() > 0:
            return _click_and_wait(page, button, timeout_ms=timeout_ms)
        link = surface.get_by_role("link", name=pattern).first
        if link.count() > 0:
            return _click_and_wait(page, link, timeout_ms=timeout_ms)
        visible_button = surface.locator("button:visible").filter(has_text=pattern).first
        if visible_button.count() > 0:
            return _click_and_wait(page, visible_button, timeout_ms=timeout_ms)
        visible_link = surface.locator("a:visible").filter(has_text=pattern).first
        if visible_link.count() > 0:
            return _click_and_wait(page, visible_link, timeout_ms=timeout_ms)
    return None


def _complete_visible_checklist(surface: Any, page: Page) -> str | None:
    checkboxes = surface.locator("input[type='checkbox']:visible")
    if checkboxes.count() == 0:
        return None

    checked_any = False
    for index in range(checkboxes.count()):
        checkbox = checkboxes.nth(index)
        if checkbox.is_checked():
            continue
        checkbox.locator("xpath=ancestor::label[1]").click(force=True)
        checked_any = True
        page.wait_for_timeout(250)

    if checked_any:
        page.wait_for_timeout(1000)
        return "complete visible checklist"
    return None


def _apply_direct_navigation(*, page: Page, observation: PageObservation, plan: CapturePlan, result: AutopilotRunResult) -> str | None:
    if observation.page_kind == PageKind.CATALOG:
        target_basename = _basename_from_url(plan.source_url)
        locator = page.locator(f"a[href='{target_basename}']").first
        return _click_and_wait(page, locator)

    if observation.page_kind == PageKind.COURSE_OVERVIEW:
        locator = page.get_by_role("button", name="Start Course").first
        return _click_and_wait(page, locator)

    if observation.page_kind == PageKind.LESSON_LIST:
        next_basename = _find_next_lesson_basename(plan, result)
        if next_basename is None:
            return None
        locator = page.locator(f"a[href='{next_basename}']").first
        return _click_and_wait(page, locator)

    if observation.page_kind == PageKind.LESSON_STATIC_TEXT:
        locator = page.get_by_role("button", name="Next").first
        return _click_and_wait(page, locator)

    if observation.page_kind == PageKind.REPORT_TABLE:
        locator = page.get_by_role("link", name="Completion Page").first
        return _click_and_wait(page, locator)

    return None


def _apply_live_navigation(*, page: Page, surface: Any, observation: PageObservation, plan: CapturePlan, result: AutopilotRunResult) -> str | None:
    if observation.page_kind in {PageKind.CATALOG, PageKind.ASSIGNED_LEARNING}:
        target_basename = _basename_from_url(plan.source_url)
        locator = page.locator(f"a[href*='{target_basename}']").first
        if locator.count() > 0:
            return _click_and_wait(page, locator)
        return _click_candidate(page, page, [plan.course_title, "open course", "launch", "view course"])

    if observation.page_kind == PageKind.COURSE_OVERVIEW:
        return _click_candidate(surface, page, ["start quiz", "start course", "^start$", "begin", "resume", "launch", "continue", "open course"])

    if observation.page_kind == PageKind.LESSON_LIST:
        checklist_action = _complete_visible_checklist(surface, page)
        if checklist_action:
            return checklist_action
        for lesson_url in plan.lesson_urls:
            if lesson_url in result.visited_logical_urls:
                continue
            lesson_basename = _basename_from_url(lesson_url)
            locator = surface.locator(f"a[href*='{lesson_basename}']").first
            if locator.count() > 0:
                return _click_and_wait(page, locator)
        return _click_candidate(surface, page, ["start quiz", "continue", "next", "^start$", "start course"])

    if observation.page_kind == PageKind.LESSON_INTERACTION_GATE:
        checklist_action = _complete_visible_checklist(surface, page)
        if checklist_action:
            return checklist_action
        return _click_candidate(surface, page, ["continue", "next", "complete", "finish"])

    if observation.page_kind in {PageKind.LESSON_STATIC_TEXT, PageKind.QUIZ_FEEDBACK, PageKind.REPORT_TABLE}:
        checklist_action = _complete_visible_checklist(surface, page)
        if checklist_action:
            return checklist_action
        return _click_candidate(surface, page, ["start quiz", "next", "continue", "complete", "finish", "return to catalog"])

    if observation.page_kind == PageKind.QUIZ_INTRO:
        return _click_candidate(surface, page, ["start quiz", "^start$", "begin quiz"])

    if observation.page_kind == PageKind.QUIZ_QUESTION:
        checklist_action = _complete_visible_checklist(surface, page)
        if checklist_action:
            return checklist_action
        return _click_candidate(surface, page, ["submit", "next", "continue"])

    if observation.page_kind == PageKind.QUIZ_RESULTS:
        return _click_candidate(surface, page, ["next", "continue", "finish", "complete", "return to catalog"])

    return None


def run_fixture_autopilot(
    *,
    plan: CapturePlan,
    fixture_root: str | Path,
    artifact_root: str | Path,
    headless: bool = True,
    start_url_override: str | None = None,
    max_steps: int = 20,
    media_controller: FixtureMediaController | None = None,
    quiz_controller: FixtureQuizController | None = None,
    recorder_provider: RecorderProvider | None = None,
) -> AutopilotRunResult:
    fixture_root_path = Path(fixture_root).resolve()
    artifact_root_path = Path(artifact_root).resolve()
    screenshot_dir = artifact_root_path / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    logical_url_map = _build_logical_url_map(plan, start_url_override=start_url_override)
    result = AutopilotRunResult(
        course_title=plan.course_title,
        planned_source_url=plan.source_url,
        artifact_root=str(artifact_root_path),
    )

    start = perf_counter()
    result.events.append(
        RunnerEvent(
            event_type=RunnerEventType.RUN_STARTED,
            timestamp_ms=0,
            logical_url=start_url_override or plan.source_url,
            detail="fixture_autopilot_started",
        )
    )

    recorder_session: RecorderSession | None = None
    if recorder_provider is not None:
        recorder_session = recorder_provider.start(
            RecorderStartRequest(
                artifact_root=str(artifact_root_path),
                course_title=plan.course_title,
                recorder_profile=plan.recorder_profile,
            )
        )
        result.recorder_session = recorder_session
        result.events.append(
            RunnerEvent(
                event_type=RunnerEventType.RECORDER_START,
                timestamp_ms=_timestamp_ms(start),
                logical_url=start_url_override or plan.source_url,
                detail=recorder_session.provider_name,
            )
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page()
            execution_url = _resolve_execution_url(start_url_override or plan.source_url, fixture_root_path)
            page.goto(execution_url, wait_until="domcontentloaded")

            for step_index in range(max_steps):
                execution_basename = _basename_from_url(page.url)
                logical_url = logical_url_map.get(execution_basename)

                snapshot, observation = _capture_page(
                    page=page,
                    step_index=step_index,
                    screenshot_dir=screenshot_dir,
                    logical_url=logical_url,
                    classifier=classify_fixture_page,
                )
                result.page_snapshots.append(snapshot)
                result.observations.append(observation)
                _record_page_visit(result, page.url, logical_url)

                timestamp_ms = _timestamp_ms(start)
                result.events.extend(
                    [
                        RunnerEvent(
                            event_type=RunnerEventType.PAGE_LOAD,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail=observation.title or observation.page_kind.value,
                        ),
                        RunnerEvent(
                            event_type=RunnerEventType.SCREENSHOT_CAPTURED,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            screenshot_uri=snapshot.screenshot_uri,
                        ),
                    ]
                )

                decision = decide_next_action(observation)
                _record_decision(result, observation, decision, logical_url)
                result.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.DECISION_MADE,
                        timestamp_ms=timestamp_ms,
                        execution_url=page.url,
                        logical_url=logical_url,
                        page_kind=observation.page_kind,
                        detail=f"{decision.action.value}:{decision.reason}",
                    )
                )

                if observation.page_kind == PageKind.COMPLETION_PAGE:
                    result.completion_detected = True
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.RUN_COMPLETED,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail="completion_detected",
                        )
                    )
                    break

                if observation.page_kind in {PageKind.LESSON_VIDEO, PageKind.LESSON_AUDIO}:
                    if media_controller is None:
                        result.stopped_reason = "media_controller_required"
                        result.events.append(
                            RunnerEvent(
                                event_type=RunnerEventType.RUN_STOPPED,
                                timestamp_ms=timestamp_ms,
                                execution_url=page.url,
                                logical_url=logical_url,
                                page_kind=observation.page_kind,
                                detail=result.stopped_reason,
                            )
                        )
                        break

                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.MEDIA_CONTROLLER_HANDOFF,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail="delegate_media_page",
                        )
                    )
                    result.events.extend(
                        media_controller.handle(
                            page=page,
                            observation=observation,
                            screenshot_dir=screenshot_dir,
                            logical_url=logical_url,
                            timestamp_ms=timestamp_ms,
                        )
                    )
                    page.wait_for_load_state("domcontentloaded")
                    continue

                if observation.page_kind == PageKind.QUIZ_QUESTION:
                    if quiz_controller is None:
                        result.stopped_reason = "quiz_controller_required"
                        result.events.append(
                            RunnerEvent(
                                event_type=RunnerEventType.RUN_STOPPED,
                                timestamp_ms=timestamp_ms,
                                execution_url=page.url,
                                logical_url=logical_url,
                                page_kind=observation.page_kind,
                                detail=result.stopped_reason,
                            )
                        )
                        break

                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.QUIZ_CONTROLLER_HANDOFF,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail="delegate_quiz_page",
                        )
                    )
                    result.events.extend(
                        quiz_controller.handle(
                            page=page,
                            observation=observation,
                            screenshot_dir=screenshot_dir,
                            logical_url=logical_url,
                            timestamp_ms=timestamp_ms,
                        )
                    )
                    page.wait_for_load_state("domcontentloaded")
                    continue

                clicked_label = _apply_direct_navigation(page=page, observation=observation, plan=plan, result=result)
                if clicked_label:
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.CLICK,
                            timestamp_ms=_timestamp_ms(start),
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail=clicked_label,
                        )
                    )
                    continue

                if observation.page_kind == PageKind.UNKNOWN:
                    result.unknown_ui_state_detected = True
                    result.stopped_reason = "unknown_ui_state"
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.UNKNOWN_UI_STATE,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail="unknown_page_kind",
                        )
                    )
                    break

                result.stopped_reason = "no_direct_navigation_available"
                result.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.RUN_STOPPED,
                        timestamp_ms=timestamp_ms,
                        execution_url=page.url,
                        logical_url=logical_url,
                        page_kind=observation.page_kind,
                        detail=result.stopped_reason,
                    )
                )
                break
            else:
                result.stopped_reason = "max_steps_exceeded"
                result.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.RUN_STOPPED,
                        timestamp_ms=_timestamp_ms(start),
                        detail=result.stopped_reason,
                    )
                )
            browser.close()
    finally:
        if recorder_provider is not None and recorder_session is not None:
            recorder_session = recorder_provider.stop(recorder_session)
            result.recorder_session = recorder_session
            result.events.append(
                RunnerEvent(
                    event_type=RunnerEventType.RECORDER_STOP,
                    timestamp_ms=_timestamp_ms(start),
                    detail=recorder_session.provider_name,
                )
            )

    return result


def run_visible_session_autopilot(
    *,
    plan: CapturePlan,
    artifact_root: str | Path,
    storage_state_path: str | Path,
    headless: bool = True,
    max_steps: int = 20,
    recorder_provider: RecorderProvider | None = None,
) -> AutopilotRunResult:
    artifact_root_path = Path(artifact_root).resolve()
    screenshot_dir = artifact_root_path / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    logical_url_map = _build_logical_url_map(plan)
    result = AutopilotRunResult(
        course_title=plan.course_title,
        planned_source_url=plan.source_url,
        artifact_root=str(artifact_root_path),
    )

    start = perf_counter()
    repeated_signature: str | None = None
    repeated_count = 0
    result.events.append(
        RunnerEvent(
            event_type=RunnerEventType.RUN_STARTED,
            timestamp_ms=0,
            logical_url=plan.source_url,
            detail="visible_session_autopilot_started",
        )
    )

    recorder_session: RecorderSession | None = None
    if recorder_provider is not None:
        recorder_session = recorder_provider.start(
            RecorderStartRequest(
                artifact_root=str(artifact_root_path),
                course_title=plan.course_title,
                recorder_profile=plan.recorder_profile,
            )
        )
        result.recorder_session = recorder_session
        result.events.append(
            RunnerEvent(
                event_type=RunnerEventType.RECORDER_START,
                timestamp_ms=_timestamp_ms(start),
                logical_url=plan.source_url,
                detail=recorder_session.provider_name,
            )
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(Path(storage_state_path).resolve()))
            page = context.new_page()
            page.goto(plan.source_url, wait_until="domcontentloaded")

            for step_index in range(max_steps):
                capture_surface = _wait_for_live_page_ready(page)
                execution_basename = _basename_from_url(page.url)
                logical_url = logical_url_map.get(execution_basename, page.url)

                snapshot, observation = _capture_page(
                    page=page,
                    step_index=step_index,
                    screenshot_dir=screenshot_dir,
                    logical_url=logical_url,
                    classifier=classify_visible_page,
                    capture_surface=capture_surface,
                )
                result.page_snapshots.append(snapshot)
                result.observations.append(observation)
                _record_page_visit(result, page.url, logical_url)
                result.active_capture_surface = (
                    f"{snapshot.active_capture_surface_type}:{snapshot.active_capture_surface_name or snapshot.active_capture_surface_url or snapshot.execution_url}"
                )

                timestamp_ms = _timestamp_ms(start)
                result.events.extend(
                    [
                        RunnerEvent(
                            event_type=RunnerEventType.PAGE_LOAD,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail=observation.title or observation.page_kind.value,
                        ),
                        RunnerEvent(
                            event_type=RunnerEventType.SCREENSHOT_CAPTURED,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            screenshot_uri=snapshot.screenshot_uri,
                        ),
                    ]
                )

                signature = _state_signature(snapshot, observation)
                if signature == repeated_signature:
                    repeated_count += 1
                else:
                    repeated_signature = signature
                    repeated_count = 1

                if repeated_count >= _REPEATED_STATE_THRESHOLD:
                    result.unknown_ui_state_detected = True
                    result.failure_category = FailureCategory.REPEATED_SAME_STATE
                    result.stopped_reason = "repeated_same_state"
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.RUN_STOPPED,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail=result.stopped_reason,
                            screenshot_uri=snapshot.screenshot_uri,
                        )
                    )
                    break

                decision = decide_next_action(observation)
                _record_decision(result, observation, decision, logical_url)
                result.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.DECISION_MADE,
                        timestamp_ms=timestamp_ms,
                        execution_url=page.url,
                        logical_url=logical_url,
                        page_kind=observation.page_kind,
                        detail=f"{decision.action.value}:{decision.reason}",
                    )
                )

                if observation.page_kind in {PageKind.AUTH_REQUIRED, PageKind.UNKNOWN}:
                    result.unknown_ui_state_detected = True
                    result.failure_category = (
                        FailureCategory.AUTH_REQUIRED if observation.page_kind == PageKind.AUTH_REQUIRED else FailureCategory.UNKNOWN_UI_STATE
                    )
                    result.stopped_reason = "auth_required" if observation.page_kind == PageKind.AUTH_REQUIRED else "unknown_ui_state"
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.UNKNOWN_UI_STATE,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail=result.stopped_reason,
                            screenshot_uri=snapshot.screenshot_uri,
                        )
                    )
                    break

                if observation.page_kind == PageKind.COURSE_SHELL_LOADING:
                    result.failure_category = FailureCategory.SHELL_READY_BUT_FRAME_LOADING
                    result.stopped_reason = "course_shell_loading"
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.RUN_STOPPED,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail=result.stopped_reason,
                            screenshot_uri=snapshot.screenshot_uri,
                        )
                    )
                    break

                if observation.page_kind == PageKind.SCORM_FRAME_LOADING:
                    result.failure_category = FailureCategory.SCORM_FRAME_NOT_READY
                    result.stopped_reason = "scorm_frame_loading"
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.RUN_STOPPED,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail=result.stopped_reason,
                            screenshot_uri=snapshot.screenshot_uri,
                        )
                    )
                    break

                if observation.page_kind == PageKind.COMPLETION_PAGE:
                    result.completion_detected = True
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.RUN_COMPLETED,
                            timestamp_ms=timestamp_ms,
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail="completion_detected",
                            screenshot_uri=snapshot.screenshot_uri,
                        )
                    )
                    break

                clicked_label = _apply_live_navigation(
                    page=page,
                    surface=capture_surface,
                    observation=observation,
                    plan=plan,
                    result=result,
                )
                if clicked_label:
                    result.events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.CLICK,
                            timestamp_ms=_timestamp_ms(start),
                            execution_url=page.url,
                            logical_url=logical_url,
                            page_kind=observation.page_kind,
                            detail=clicked_label,
                        )
                    )
                    continue

                if observation.page_kind == PageKind.LESSON_INTERACTION_GATE:
                    result.failure_category = FailureCategory.LESSON_GATE_UNHANDLED
                    result.stopped_reason = "lesson_gate_unhandled"
                elif observation.page_kind == PageKind.QUIZ_RESULTS:
                    result.failure_category = FailureCategory.QUIZ_RESULTS_EXIT_UNHANDLED
                    result.stopped_reason = "quiz_results_exit_unhandled"
                elif any(button.strip().lower() == "skip to lesson" for button in snapshot.buttons) and any(
                    button.strip().lower() in {"next", "continue", "submit"} for button in snapshot.buttons
                ):
                    result.failure_category = FailureCategory.SELECTOR_PRIORITY_MISFIRE
                    result.stopped_reason = "selector_priority_misfire"
                else:
                    result.failure_category = FailureCategory.NO_LIVE_NAVIGATION_AVAILABLE
                    result.stopped_reason = "no_live_navigation_available"

                result.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.RUN_STOPPED,
                        timestamp_ms=timestamp_ms,
                        execution_url=page.url,
                        logical_url=logical_url,
                        page_kind=observation.page_kind,
                        detail=result.stopped_reason,
                        screenshot_uri=snapshot.screenshot_uri,
                    )
                )
                break
            else:
                result.failure_category = FailureCategory.REPEATED_SAME_STATE
                result.stopped_reason = "max_steps_exceeded"
                result.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.RUN_STOPPED,
                        timestamp_ms=_timestamp_ms(start),
                        detail=result.stopped_reason,
                    )
                )
            browser.close()
    finally:
        if recorder_provider is not None and recorder_session is not None:
            recorder_session = recorder_provider.stop(recorder_session)
            result.recorder_session = recorder_session
            result.events.append(
                RunnerEvent(
                    event_type=RunnerEventType.RECORDER_STOP,
                    timestamp_ms=_timestamp_ms(start),
                    detail=recorder_session.provider_name,
                )
            )

    return result
