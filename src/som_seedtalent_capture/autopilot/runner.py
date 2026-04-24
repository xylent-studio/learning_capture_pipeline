from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Protocol
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright
from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import CapturePlan
from som_seedtalent_capture.autopilot.page_classifier import VisibleDomSnapshot, classify_fixture_page
from som_seedtalent_capture.autopilot.state_machine import CaptureDecision, NavigationAction, PageKind, PageObservation, decide_next_action


class RunnerEventType(StrEnum):
    RUN_STARTED = "run_started"
    PAGE_LOAD = "page_load"
    SCREENSHOT_CAPTURED = "screenshot_captured"
    DECISION_MADE = "decision_made"
    CLICK = "click"
    MEDIA_CONTROLLER_HANDOFF = "media_controller_handoff"
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
    title: str | None = None
    visible_text: str = ""
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
    page_snapshots: list[RunnerPageSnapshot] = Field(default_factory=list)
    observations: list[PageObservation] = Field(default_factory=list)
    decisions: list[RunnerDecisionRecord] = Field(default_factory=list)
    events: list[RunnerEvent] = Field(default_factory=list)
    visited_execution_urls: list[str] = Field(default_factory=list)
    visited_logical_urls: list[str] = Field(default_factory=list)
    completion_detected: bool = False
    unknown_ui_state_detected: bool = False
    stopped_reason: str | None = None


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


def _extract_visible_snapshot(page: Page) -> VisibleDomSnapshot:
    visible_text = page.locator("body").inner_text()
    buttons = [text.strip() for text in page.locator("button:visible").all_inner_texts() if text.strip()]
    links = [text.strip() for text in page.locator("a:visible").all_inner_texts() if text.strip()]
    media_state = page.evaluate(
        """() => {
            const media = document.querySelector('video, audio');
            return {
              dataPageKind: document.body?.dataset?.pageKind ?? null,
              count: document.querySelectorAll('video, audio').length,
              durationSeconds: media && Number.isFinite(media.duration) ? media.duration : null,
              currentTimeSeconds: media && Number.isFinite(media.currentTime) ? media.currentTime : null,
              paused: media ? media.paused : null,
            };
        }"""
    )

    return VisibleDomSnapshot(
        title=page.title(),
        data_page_kind=media_state["dataPageKind"],
        visible_text=visible_text,
        buttons=buttons,
        links=links,
        media={
            "count": media_state["count"],
            "duration_seconds": media_state["durationSeconds"],
            "current_time_seconds": media_state["currentTimeSeconds"],
            "paused": media_state["paused"],
        },
    )


def _capture_page(
    *,
    page: Page,
    step_index: int,
    screenshot_dir: Path,
    logical_url: str | None,
) -> tuple[RunnerPageSnapshot, PageObservation]:
    screenshot_uri = str((screenshot_dir / f"step-{step_index:03d}.png").resolve())
    page.screenshot(path=screenshot_uri, full_page=True)
    snapshot = _extract_visible_snapshot(page)
    observation = classify_fixture_page(url=page.url, snapshot=snapshot, screenshot_uri=screenshot_uri)
    runner_snapshot = RunnerPageSnapshot(
        execution_url=page.url,
        logical_url=logical_url,
        title=snapshot.title,
        visible_text=snapshot.visible_text,
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
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    return label


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

    return result
