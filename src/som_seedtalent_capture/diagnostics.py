from __future__ import annotations

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.runner import RunnerPageSnapshot
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
from som_seedtalent_capture.config import SelectorTuningConfig


class RealPageDiagnostics(BaseModel):
    url: str
    title: str | None = None
    page_kind: PageKind
    confidence: float = Field(ge=0.0, le=1.0)
    visible_buttons: list[str] = Field(default_factory=list)
    visible_links: list[str] = Field(default_factory=list)
    screenshot_uri: str | None = None
    prohibited_path_detected: bool = False
    unknown_ui_state: bool = False
    visible_locator_preferences: list[str] = Field(default_factory=list)
    navigation_timeout_ms: int
    unchanged_screen_timeout_ms: int
    max_click_retries: int


def build_page_diagnostics(
    *,
    observation: PageObservation,
    snapshot: RunnerPageSnapshot,
    tuning: SelectorTuningConfig,
) -> RealPageDiagnostics:
    prohibited_path_detected = any(pattern in observation.url for pattern in tuning.prohibited_path_patterns)
    return RealPageDiagnostics(
        url=observation.url,
        title=observation.title,
        page_kind=observation.page_kind,
        confidence=observation.confidence,
        visible_buttons=snapshot.buttons,
        visible_links=snapshot.links,
        screenshot_uri=snapshot.screenshot_uri,
        prohibited_path_detected=prohibited_path_detected,
        unknown_ui_state=observation.page_kind == PageKind.UNKNOWN,
        visible_locator_preferences=tuning.visible_locator_preferences,
        navigation_timeout_ms=tuning.navigation_timeout_ms,
        unchanged_screen_timeout_ms=tuning.unchanged_screen_timeout_ms,
        max_click_retries=tuning.max_click_retries,
    )
