from pathlib import Path

import pytest
from playwright.sync_api import Error, sync_playwright

from som_seedtalent_capture.autopilot.capture_plan import QuizCaptureMode, build_fixture_capture_plan_from_file
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.media_controller import FixtureMediaController
from som_seedtalent_capture.autopilot.quiz_controller import FixtureQuizController, LiveQuizController, QuizEvidenceSnippet
from som_seedtalent_capture.autopilot.runner import run_fixture_autopilot
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
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


def test_quiz_controller_capture_only_stays_on_question_page(tmp_path: Path):
    _ensure_chromium_or_skip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto((FIXTURE_ROOT / "quiz.html").resolve().as_uri(), wait_until="domcontentloaded")

        controller = FixtureQuizController(mode=QuizCaptureMode.CAPTURE_ONLY)
        result = controller.run(
            page=page,
            observation=PageObservation(url=page.url, page_kind=PageKind.QUIZ_QUESTION),
            screenshot_dir=tmp_path,
            logical_url="https://app.seedtalent.com/quiz.html",
            timestamp_ms=123,
        )
        browser.close()

    assert result.question_text == "Which action should happen before opening the floor?"
    assert len(result.options) == 3
    assert result.feedback_text is None
    assert result.advanced_to_next is False
    assert result.answer_strategy == "capture_only"
    assert Path(result.question_screenshot_uri).exists()


def test_quiz_controller_capture_and_complete_records_feedback(tmp_path: Path):
    _ensure_chromium_or_skip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto((FIXTURE_ROOT / "quiz.html").resolve().as_uri(), wait_until="domcontentloaded")

        controller = FixtureQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)
        result = controller.run(
            page=page,
            observation=PageObservation(url=page.url, page_kind=PageKind.QUIZ_QUESTION),
            screenshot_dir=tmp_path,
            logical_url="https://app.seedtalent.com/quiz.html",
            timestamp_ms=456,
        )
        browser.close()

    assert result.selected_answers == ["Confirm the counter area is clear"]
    assert "Correct" in (result.feedback_text or "")
    assert result.advanced_to_next is True
    assert result.attempts_used == 1
    assert Path(result.question_screenshot_uri).exists()
    assert Path(result.feedback_screenshot_uri or "").exists()


def test_quiz_controller_model_assisted_stub_stops_cleanly(tmp_path: Path):
    _ensure_chromium_or_skip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto((FIXTURE_ROOT / "quiz.html").resolve().as_uri(), wait_until="domcontentloaded")

        controller = FixtureQuizController(mode=QuizCaptureMode.MODEL_ASSISTED_ANSWER)
        result = controller.run(
            page=page,
            observation=PageObservation(url=page.url, page_kind=PageKind.QUIZ_QUESTION),
            screenshot_dir=tmp_path,
            logical_url="https://app.seedtalent.com/quiz.html",
            timestamp_ms=789,
        )
        browser.close()

    assert result.advanced_to_next is False
    assert result.stopped_reason == "model_assisted_answer_not_implemented"
    assert result.feedback_text is None


def test_live_quiz_controller_uses_evidence_grounded_answering(tmp_path: Path):
    _ensure_chromium_or_skip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto((FIXTURE_ROOT / "quiz.html").resolve().as_uri(), wait_until="domcontentloaded")

        controller = LiveQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)
        result = controller.run(
            page=page,
            surface=page,
            observation=PageObservation(url=page.url, page_kind=PageKind.QUIZ_QUESTION),
            screenshot_dir=tmp_path,
            logical_url="https://app.seedtalent.com/quiz.html",
            timestamp_ms=654,
            evidence_snippets=[
                QuizEvidenceSnippet(
                    source_reference="lesson-static",
                    text="Before opening the floor, confirm the counter area is clear and hazards are removed.",
                )
            ],
        )
        browser.close()

    assert result.selected_answers == ["Confirm the counter area is clear"]
    assert result.answer_strategy == "evidence_grounded"
    assert result.confidence >= 0.75


def test_live_quiz_controller_falls_back_to_select_all_for_multi_select(tmp_path: Path):
    class _FakeLocator:
        def __init__(self, *, body_text: str = "", values: list[str] | None = None) -> None:
            self._body_text = body_text
            self._values = values or []

        def inner_text(self) -> str:
            return self._body_text

        def all_inner_texts(self) -> list[str]:
            return self._values

        @property
        def first(self):
            return self

        def count(self) -> int:
            return 0

        def filter(self, has_text):  # noqa: ANN001
            return self

    class _FakeSurface:
        def locator(self, selector: str):
            if selector == "body":
                return _FakeLocator(
                    body_text=(
                        "Question 01/02\n"
                        "Seed & Strain consumers... (select all that apply)\n"
                        "Are passionate about quality\n"
                        "Are regular cannabis users\n"
                        "Seek unique flower characteristics\n"
                        "Submit"
                    )
                )
            if selector == "h1:visible, h2:visible, h3:visible":
                return _FakeLocator(values=["Question 01/02"])
            if selector == "label:visible":
                return _FakeLocator(
                    values=[
                        "Are passionate about quality",
                        "Are regular cannabis users",
                        "Seek unique flower characteristics",
                    ]
                )
            if selector == "button:visible":
                return _FakeLocator(values=["Submit"])
            if selector == "button, a, [role='button']":
                return _FakeLocator(values=[])
            raise AssertionError(selector)

        def get_by_label(self, pattern):  # noqa: ANN001
            class _LabelLocator:
                @property
                def first(self):
                    return self

                def count(self):
                    return 0

                def click(self, force: bool = False):  # noqa: ARG002
                    return None

            return _LabelLocator()

    class _FakePage:
        url = "https://app.seedtalent.com/course/example"

        def screenshot(self, path: str, full_page: bool = True):  # noqa: ARG002
            Path(path).write_text("image", encoding="utf-8")

        def wait_for_timeout(self, timeout_ms: int):  # noqa: ARG002
            return None

    controller = LiveQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)
    result = controller.run(
        page=_FakePage(),
        surface=_FakeSurface(),
        observation=PageObservation(url="https://app.seedtalent.com/course/example", page_kind=PageKind.QUIZ_QUESTION),
        screenshot_dir=tmp_path,
        logical_url="https://app.seedtalent.com/course/example",
        timestamp_ms=701,
        evidence_snippets=[],
    )

    assert result.selected_answers == [
        "Are passionate about quality",
        "Are regular cannabis users",
        "Seek unique flower characteristics",
    ]
    assert result.answer_strategy == "fallback_select_all"


def test_live_quiz_controller_results_state_prefers_next_over_take_again(monkeypatch, tmp_path: Path):
    del monkeypatch

    class _FakeSurface:
        def __init__(self) -> None:
            self._buttons = [
                {"text": "NEXT", "visible": True, "enabled": False, "aria_hidden": "true", "aria_disabled": "true", "class_name": "visually-hidden-always"},
                {"text": "CONTINUE", "visible": True, "enabled": True, "aria_hidden": "false", "aria_disabled": "false", "class_name": ""},
                {"text": "TAKE AGAIN", "visible": True, "enabled": True, "aria_hidden": "false", "aria_disabled": "false", "class_name": ""},
            ]

        def locator(self, selector: str):
            class _Locator:
                def __init__(self, values):
                    self._values = values

                def inner_text(self):
                    return "Quiz Results\nYour score 0%\nFailed"

                def all_inner_texts(self):
                    return [value["text"] for value in self._values]

                @property
                def first(self):
                    return _ClickLocator(self._values[0] if self._values else None)

                def count(self):
                    return len(self._values)

                def nth(self, index: int):
                    return _ClickLocator(self._values[index])

                def filter(self, has_text):  # noqa: ANN001
                    for value in self._values:
                        if has_text.search(value["text"]):
                            return _Locator([value])
                    return _Locator([])

            if selector == "body":
                return _Locator([])
            if selector == "h1:visible, h2:visible, h3:visible":
                return _Locator([{"text": "Quiz Results"}])
            if selector == "label:visible":
                return _Locator([])
            if selector == "button:visible":
                return _Locator(self._buttons)
            if selector == "button, a, [role='button']":
                return _Locator(self._buttons)
            raise AssertionError(selector)

        def get_by_role(self, role: str, name):  # noqa: ANN001
            if role != "button":
                return _ClickLocator(None)
            for button in self._buttons:
                if name.search(button["text"]):
                    return _ClickLocator(button)
            return _ClickLocator(None)

    class _ClickLocator:
        def __init__(self, button: dict[str, str | bool] | None) -> None:
            self._button = button

        @property
        def first(self):
            return self

        def count(self):
            return 1 if self._button else 0

        def inner_text(self):
            return "" if self._button is None else str(self._button["text"])

        def is_visible(self):
            return False if self._button is None else bool(self._button["visible"])

        def is_enabled(self):
            return False if self._button is None else bool(self._button["enabled"])

        def get_attribute(self, name: str):
            if self._button is None:
                return None
            if name == "aria-hidden":
                return str(self._button["aria_hidden"])
            if name == "aria-disabled":
                return str(self._button["aria_disabled"])
            if name == "class":
                return str(self._button["class_name"])
            return None

        def scroll_into_view_if_needed(self, timeout: int = 0):  # noqa: ARG002
            return None

        def click(self, force: bool = False, timeout: int = 0):  # noqa: ARG002
            return None

    class _FakePage:
        url = "https://app.seedtalent.com/course/example"

        def screenshot(self, path: str, full_page: bool = True):  # noqa: ARG002
            Path(path).write_text("image", encoding="utf-8")

        def wait_for_timeout(self, timeout_ms: int):  # noqa: ARG002
            return None

    controller = LiveQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)
    result = controller.run(
        page=_FakePage(),
        surface=_FakeSurface(),
        observation=PageObservation(url="https://app.seedtalent.com/course/example", page_kind=PageKind.QUIZ_RESULTS),
        screenshot_dir=tmp_path,
        logical_url="https://app.seedtalent.com/course/example",
        timestamp_ms=777,
        evidence_snippets=[],
    )

    assert result.applied_action_label == "CONTINUE"
    assert result.advanced_to_next is True


def test_live_quiz_controller_resets_feedback_state_before_retry(tmp_path: Path):
    class _ButtonLocator:
        def __init__(self, values: list[dict[str, str | bool]]) -> None:
            self._values = values

        def filter(self, has_text):  # noqa: ANN001
            return _ButtonLocator([value for value in self._values if has_text.search(str(value["text"]))])

        def count(self) -> int:
            return len(self._values)

        def nth(self, index: int):
            return _SingleButtonLocator(self._values[index])

    class _SingleButtonLocator:
        def __init__(self, value: dict[str, str | bool]) -> None:
            self._value = value

        def inner_text(self):
            return str(self._value["text"])

        def is_visible(self):
            return bool(self._value["visible"])

        def is_enabled(self):
            return bool(self._value["enabled"])

        def get_attribute(self, name: str):
            if name == "aria-hidden":
                return "false"
            if name == "aria-disabled":
                return "false"
            if name == "class":
                return ""
            return None

        def scroll_into_view_if_needed(self, timeout: int = 0):  # noqa: ARG002
            return None

        def click(self, timeout: int = 0):  # noqa: ARG002
            self._value["clicked"] = True
            return None

    class _StaticLocator:
        def __init__(self, *, body_text: str = "", values: list[str] | None = None) -> None:
            self._body_text = body_text
            self._values = values or []

        def inner_text(self) -> str:
            return self._body_text

        def all_inner_texts(self) -> list[str]:
            return self._values

        @property
        def first(self):
            return self

        def count(self) -> int:
            return 0

        def filter(self, has_text):  # noqa: ANN001
            del has_text
            return self

    buttons = [
        {"text": "TAKE AGAIN", "visible": True, "enabled": True},
        {"text": "SUBMIT", "visible": True, "enabled": True},
    ]

    class _FakeSurface:
        def locator(self, selector: str):
            if selector == "body":
                return _StaticLocator(
                    body_text=(
                        "Incorrect. Correct answer: Clean and well-run cultivation centers. "
                        "Your answer: The highest THC %. TAKE AGAIN SUBMIT"
                    )
                )
            if selector == "h1:visible, h2:visible, h3:visible":
                return _StaticLocator(values=["Question 01/02"])
            if selector == "label:visible":
                return _StaticLocator(values=["Clean and well-run cultivation centers", "The highest THC %"])
            if selector == "button:visible":
                return _StaticLocator(values=[str(button["text"]) for button in buttons])
            if selector == "button, a, [role='button']":
                return _ButtonLocator(buttons)
            raise AssertionError(selector)

        def get_by_label(self, pattern):  # noqa: ANN001
            del pattern

            class _NoopLabel:
                @property
                def first(self):
                    return self

                def count(self):
                    return 0

                def click(self, force: bool = False):  # noqa: ARG002
                    return None

            return _NoopLabel()

    class _FakePage:
        url = "https://app.seedtalent.com/course/example"

        def screenshot(self, path: str, full_page: bool = True):  # noqa: ARG002
            Path(path).write_text("image", encoding="utf-8")

        def wait_for_timeout(self, timeout_ms: int):  # noqa: ARG002
            return None

    controller = LiveQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)
    result = controller.run(
        page=_FakePage(),
        surface=_FakeSurface(),
        observation=PageObservation(url="https://app.seedtalent.com/course/example", page_kind=PageKind.QUIZ_QUESTION),
        screenshot_dir=tmp_path,
        logical_url="https://app.seedtalent.com/course/example",
        timestamp_ms=880,
        evidence_snippets=[],
    )

    assert result.answer_strategy == "feedback_retry_reset"
    assert result.applied_action_label == "TAKE AGAIN"
    assert result.feedback_changed_retry is True


def test_live_quiz_controller_prefers_next_over_retry_on_feedback_marked_question(tmp_path: Path):
    class _ButtonLocator:
        def __init__(self, values: list[dict[str, str | bool]]) -> None:
            self._values = values

        def filter(self, has_text):  # noqa: ANN001
            return _ButtonLocator([value for value in self._values if has_text.search(str(value["text"]))])

        def count(self) -> int:
            return len(self._values)

        def nth(self, index: int):
            return _SingleButtonLocator(self._values[index])

    class _SingleButtonLocator:
        def __init__(self, value: dict[str, str | bool]) -> None:
            self._value = value

        def inner_text(self):
            return str(self._value["text"])

        def is_visible(self):
            return bool(self._value["visible"])

        def is_enabled(self):
            return bool(self._value["enabled"])

        def get_attribute(self, name: str):
            if name == "aria-hidden":
                return "false"
            if name == "aria-disabled":
                return "false"
            if name == "class":
                return ""
            return None

        def scroll_into_view_if_needed(self, timeout: int = 0):  # noqa: ARG002
            return None

        def click(self, timeout: int = 0):  # noqa: ARG002
            self._value["clicked"] = True
            return None

    class _StaticLocator:
        def __init__(self, *, body_text: str = "", values: list[str] | None = None) -> None:
            self._body_text = body_text
            self._values = values or []

        def inner_text(self) -> str:
            return self._body_text

        def all_inner_texts(self) -> list[str]:
            return self._values

        @property
        def first(self):
            return self

        def count(self) -> int:
            return 0

        def filter(self, has_text):  # noqa: ANN001
            del has_text
            return self

    buttons = [
        {"text": "NEXT", "visible": True, "enabled": True},
        {"text": "TAKE AGAIN", "visible": True, "enabled": True},
        {"text": "SUBMIT", "visible": True, "enabled": True},
    ]

    class _FakeSurface:
        def locator(self, selector: str):
            if selector == "body":
                return _StaticLocator(
                    body_text=(
                        "Incorrect. Correct answer: Clean and well-run cultivation centers. "
                        "Your answer: The highest THC %. NEXT TAKE AGAIN SUBMIT"
                    )
                )
            if selector == "h1:visible, h2:visible, h3:visible":
                return _StaticLocator(values=["Question 01/02"])
            if selector == "label:visible":
                return _StaticLocator(values=["Clean and well-run cultivation centers", "The highest THC %"])
            if selector == "button:visible":
                return _StaticLocator(values=[str(button["text"]) for button in buttons])
            if selector == "button, a, [role='button']":
                return _ButtonLocator(buttons)
            raise AssertionError(selector)

        def get_by_label(self, pattern):  # noqa: ANN001
            del pattern

            class _NoopLabel:
                @property
                def first(self):
                    return self

                def count(self):
                    return 0

                def click(self, force: bool = False):  # noqa: ARG002
                    return None

            return _NoopLabel()

    class _FakePage:
        url = "https://app.seedtalent.com/course/example"

        def screenshot(self, path: str, full_page: bool = True):  # noqa: ARG002
            Path(path).write_text("image", encoding="utf-8")

        def wait_for_timeout(self, timeout_ms: int):  # noqa: ARG002
            return None

    controller = LiveQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)
    result = controller.run(
        page=_FakePage(),
        surface=_FakeSurface(),
        observation=PageObservation(url="https://app.seedtalent.com/course/example", page_kind=PageKind.QUIZ_QUESTION),
        screenshot_dir=tmp_path,
        logical_url="https://app.seedtalent.com/course/example",
        timestamp_ms=881,
        evidence_snippets=[],
    )

    assert result.answer_strategy == "feedback_progression"
    assert result.applied_action_label == "NEXT"
    assert result.advanced_to_next is True


def test_live_quiz_controller_uses_active_question_scope_when_multiple_questions_exist(tmp_path: Path):
    class _StaticLocator:
        def __init__(self, *, body_text: str = "", values: list[str] | None = None) -> None:
            self._body_text = body_text
            self._values = values or []

        def inner_text(self) -> str:
            return self._body_text

        def all_inner_texts(self) -> list[str]:
            return self._values

        @property
        def first(self):
            return self

        def count(self) -> int:
            return 0

        def filter(self, has_text):  # noqa: ANN001
            del has_text
            return self

    question_two_options = [
        "Are passionate about quality",
        "Are regular cannabis users",
        "Seek unique flower characteristics",
        "Seek premium price points",
        "Appreciate accessible pricing",
    ]

    class _FakeSurface:
        def locator(self, selector: str):
            if selector == "body":
                return _StaticLocator(
                    body_text=(
                        "Incorrect. Correct answer: The ability to bring unique strains and products to market at an affordable price point. "
                        "Question 01/02 What is important to the Seed & Strain Growers? "
                        "Question 02/02 Seed & Strain consumers... (select all that apply) "
                        "Are passionate about quality Are regular cannabis users Seek unique flower characteristics "
                        "Seek premium price points Appreciate accessible pricing Submit Next Quiz Results"
                    )
                )
            if selector == "h1:visible, h2:visible, h3:visible":
                return _StaticLocator(values=["Question 01/02", "Question 02/02", "Quiz Results"])
            if selector == "label:visible":
                return _StaticLocator(
                    values=[
                        "The ability to bring unique strains and products to market at an affordable price point.",
                        "Clean and well-run cultivation centers",
                        "The highest THC %",
                        *question_two_options,
                    ]
                )
            if selector == "button:visible":
                return _StaticLocator(values=["SUBMIT"])
            if selector == "button, a, [role='button']":
                return _StaticLocator(values=[])
            raise AssertionError(selector)

        def get_by_label(self, pattern):  # noqa: ANN001
            del pattern

            class _NoopLabel:
                @property
                def first(self):
                    return self

                def count(self):
                    return 0

                def click(self, force: bool = False):  # noqa: ARG002
                    return None

            return _NoopLabel()

    class _FakePage:
        url = "https://app.seedtalent.com/course/example"

        def screenshot(self, path: str, full_page: bool = True):  # noqa: ARG002
            Path(path).write_text("image", encoding="utf-8")

        def wait_for_timeout(self, timeout_ms: int):  # noqa: ARG002
            return None

    controller = LiveQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)
    result = controller.run(
        page=_FakePage(),
        surface=_FakeSurface(),
        observation=PageObservation(url="https://app.seedtalent.com/course/example", page_kind=PageKind.QUIZ_QUESTION),
        screenshot_dir=tmp_path,
        logical_url="https://app.seedtalent.com/course/example",
        timestamp_ms=990,
        evidence_snippets=[],
    )

    assert result.question_text == "Seed & Strain consumers... (select all that apply)"
    assert result.options == question_two_options
    assert result.answer_strategy == "fallback_select_all"


def test_runner_reaches_completion_with_real_quiz_controller(tmp_path: Path):
    _ensure_chromium_or_skip()

    plan = _build_capture_plan()
    quiz_controller = FixtureQuizController(mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT)

    result = run_fixture_autopilot(
        plan=plan,
        fixture_root=FIXTURE_ROOT,
        artifact_root=tmp_path,
        headless=True,
        media_controller=FixtureMediaController(mock_completion=True),
        quiz_controller=quiz_controller,
    )

    assert result.completion_detected is True
    assert quiz_controller.last_result is not None
    assert quiz_controller.last_result.feedback_text is not None
    assert quiz_controller.last_result.advanced_to_next is True
