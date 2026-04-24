from som_seedtalent_capture.autopilot.state_machine import (
    NavigationAction,
    PageKind,
    PageObservation,
    decide_next_action,
)


def test_decide_video_action():
    obs = PageObservation(
        url="https://app.seedtalent.com/course/demo",
        page_kind=PageKind.LESSON_VIDEO,
        confidence=0.8,
    )
    decision = decide_next_action(obs)
    assert decision.action == NavigationAction.PLAY_MEDIA_WAIT_AND_NEXT
    assert decision.requires_human is False


def test_unknown_requires_human():
    obs = PageObservation(url="https://app.seedtalent.com/unknown")
    decision = decide_next_action(obs)
    assert decision.action == NavigationAction.RETRY_OR_ESCALATE
    assert decision.requires_human is True
