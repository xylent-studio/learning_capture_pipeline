from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page
from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.runner import RunnerEvent, RunnerEventType
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation


class MediaPlaybackState(BaseModel):
    media_tag: str
    control_label: str
    visible_next_enabled: bool
    media_element_found: bool
    current_time_seconds: float | None = None
    duration_seconds: float | None = Field(default=None, ge=0.0)
    paused: bool | None = None


class MediaControllerResult(BaseModel):
    events: list[RunnerEvent] = Field(default_factory=list)
    playback_state: MediaPlaybackState
    advanced_to_next: bool = False
    completion_mode: str = "mock_completion"


def inspect_media_playback_state(page: Page, page_kind: PageKind) -> MediaPlaybackState:
    media_tag = "video" if page_kind == PageKind.LESSON_VIDEO else "audio"
    control_label = "Play Lesson Video" if page_kind == PageKind.LESSON_VIDEO else "Play Lesson Audio"
    state = page.evaluate(
        f"""() => {{
            const media = document.querySelector('{media_tag}');
            const nextButton = Array.from(document.querySelectorAll('button')).find((button) => button.innerText.trim() === 'Next');
            return {{
              mediaElementFound: Boolean(media),
              currentTimeSeconds: media && Number.isFinite(media.currentTime) ? media.currentTime : null,
              durationSeconds: media && Number.isFinite(media.duration) ? media.duration : null,
              paused: media ? media.paused : null,
              visibleNextEnabled: nextButton ? !nextButton.disabled : false,
            }};
        }}"""
    )
    return MediaPlaybackState(
        media_tag=media_tag,
        control_label=control_label,
        visible_next_enabled=state["visibleNextEnabled"],
        media_element_found=state["mediaElementFound"],
        current_time_seconds=state["currentTimeSeconds"],
        duration_seconds=state["durationSeconds"],
        paused=state["paused"],
    )


class FixtureMediaController:
    def __init__(self, *, mock_completion: bool = True) -> None:
        self.mock_completion = mock_completion

    def handle(
        self,
        *,
        page: Page,
        observation: PageObservation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> list[RunnerEvent]:
        result = self.run(
            page=page,
            observation=observation,
            screenshot_dir=screenshot_dir,
            logical_url=logical_url,
            timestamp_ms=timestamp_ms,
        )
        return result.events

    def run(
        self,
        *,
        page: Page,
        observation: PageObservation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> MediaControllerResult:
        playback_state = inspect_media_playback_state(page, observation.page_kind)
        start_event = RunnerEvent(
            event_type=RunnerEventType.MEDIA_START,
            timestamp_ms=timestamp_ms,
            execution_url=page.url,
            logical_url=logical_url,
            page_kind=observation.page_kind,
            detail=playback_state.control_label,
        )

        page.get_by_role("button", name=playback_state.control_label).click()

        if self.mock_completion:
            page.evaluate(
                """() => {
                    const media = document.querySelector('video, audio');
                    if (media) {
                      Object.defineProperty(media, 'currentTime', { configurable: true, get: () => 1.0 });
                    }
                    window.__fixtureMediaComplete = true;
                }"""
            )

        next_locator = page.get_by_role("button", name="Next")
        advanced_to_next = next_locator.count() > 0
        if advanced_to_next:
            next_locator.first.click()
            page.wait_for_load_state("domcontentloaded")

        end_event = RunnerEvent(
            event_type=RunnerEventType.MEDIA_END,
            timestamp_ms=timestamp_ms,
            execution_url=page.url,
            logical_url=logical_url,
            page_kind=observation.page_kind,
            detail="mock_media_completion" if self.mock_completion else "visible_next_enabled",
        )

        return MediaControllerResult(
            events=[start_event, end_event],
            playback_state=playback_state,
            advanced_to_next=advanced_to_next,
            completion_mode="mock_completion" if self.mock_completion else "visible_next_enabled",
        )
