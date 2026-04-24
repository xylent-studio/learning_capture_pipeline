from som_seedtalent_capture.autopilot.runner import RunnerPageSnapshot
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
from som_seedtalent_capture.config import SelectorTuningConfig
from som_seedtalent_capture.diagnostics import build_page_diagnostics


def test_build_page_diagnostics_marks_unknown_and_prohibited_path():
    observation = PageObservation(
        url="https://app.seedtalent.com/settings",
        title="Settings",
        page_kind=PageKind.UNKNOWN,
        confidence=0.2,
        screenshot_uri="C:/captures/unknown.png",
    )
    snapshot = RunnerPageSnapshot(
        execution_url=observation.url,
        title="Settings",
        visible_text="Settings page",
        buttons=["Save"],
        links=["Back"],
        screenshot_uri="C:/captures/unknown.png",
        page_kind=PageKind.UNKNOWN,
        confidence=0.2,
    )

    diagnostics = build_page_diagnostics(
        observation=observation,
        snapshot=snapshot,
        tuning=SelectorTuningConfig(),
    )

    assert diagnostics.unknown_ui_state is True
    assert diagnostics.prohibited_path_detected is True
    assert diagnostics.visible_buttons == ["Save"]
