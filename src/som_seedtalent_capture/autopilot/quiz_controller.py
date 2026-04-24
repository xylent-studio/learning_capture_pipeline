from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page
from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import QuizCaptureMode
from som_seedtalent_capture.autopilot.runner import RunnerEvent, RunnerEventType
from som_seedtalent_capture.autopilot.state_machine import PageObservation


class QuizCaptureResult(BaseModel):
    mode: QuizCaptureMode
    question_text: str
    options: list[str] = Field(default_factory=list)
    selected_answer: str | None = None
    feedback_text: str | None = None
    question_screenshot_uri: str
    feedback_screenshot_uri: str | None = None
    attempts_used: int = Field(default=0, ge=0)
    advanced_to_next: bool = False
    stopped_reason: str | None = None


def _capture_question(page: Page, screenshot_dir: Path, timestamp_ms: int) -> tuple[str, list[str], str]:
    question_text = page.locator("form h2").inner_text().strip()
    options = [text.strip() for text in page.locator("label.quiz-option").all_inner_texts() if text.strip()]
    screenshot_uri = str((screenshot_dir / f"quiz-question-{timestamp_ms}.png").resolve())
    page.screenshot(path=screenshot_uri, full_page=True)
    return question_text, options, screenshot_uri


def _capture_feedback(page: Page, screenshot_dir: Path, timestamp_ms: int) -> tuple[str, str]:
    feedback_text = page.locator("main").inner_text().strip()
    screenshot_uri = str((screenshot_dir / f"quiz-feedback-{timestamp_ms}.png").resolve())
    page.screenshot(path=screenshot_uri, full_page=True)
    return feedback_text, screenshot_uri


class FixtureQuizController:
    def __init__(self, *, mode: QuizCaptureMode = QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT, max_attempts: int = 1) -> None:
        self.mode = mode
        self.max_attempts = max_attempts
        self.history: list[QuizCaptureResult] = []

    @property
    def last_result(self) -> QuizCaptureResult | None:
        if not self.history:
            return None
        return self.history[-1]

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

        events = [
            RunnerEvent(
                event_type=RunnerEventType.SCREENSHOT_CAPTURED,
                timestamp_ms=timestamp_ms,
                execution_url=page.url,
                logical_url=logical_url,
                page_kind=observation.page_kind,
                screenshot_uri=result.question_screenshot_uri,
                detail="quiz_question_capture",
            )
        ]
        if result.feedback_screenshot_uri:
            events.append(
                RunnerEvent(
                    event_type=RunnerEventType.SCREENSHOT_CAPTURED,
                    timestamp_ms=timestamp_ms,
                    execution_url=page.url,
                    logical_url=logical_url,
                    page_kind=observation.page_kind,
                    screenshot_uri=result.feedback_screenshot_uri,
                    detail="quiz_feedback_capture",
                )
            )
        return events

    def run(
        self,
        *,
        page: Page,
        observation: PageObservation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> QuizCaptureResult:
        question_text, options, question_screenshot_uri = _capture_question(page, screenshot_dir, timestamp_ms)

        if self.mode == QuizCaptureMode.CAPTURE_ONLY:
            result = QuizCaptureResult(
                mode=self.mode,
                question_text=question_text,
                options=options,
                question_screenshot_uri=question_screenshot_uri,
                attempts_used=0,
                advanced_to_next=False,
                stopped_reason="capture_only_mode",
            )
            self.history.append(result)
            return result

        if self.mode == QuizCaptureMode.MODEL_ASSISTED_ANSWER:
            result = QuizCaptureResult(
                mode=self.mode,
                question_text=question_text,
                options=options,
                question_screenshot_uri=question_screenshot_uri,
                attempts_used=0,
                advanced_to_next=False,
                stopped_reason="model_assisted_answer_not_implemented",
            )
            self.history.append(result)
            return result

        attempts_used = 0
        selected_answer: str | None = None
        feedback_text: str | None = None
        feedback_screenshot_uri: str | None = None
        advanced_to_next = False

        while attempts_used < self.max_attempts:
            attempts_used += 1
            selected_answer = options[0] if options else None
            if selected_answer is None:
                break

            page.locator("input[name='q1']").first.check()
            page.get_by_role("button", name="Submit").click()
            page.wait_for_load_state("domcontentloaded")

            feedback_text, feedback_screenshot_uri = _capture_feedback(page, screenshot_dir, timestamp_ms)
            continue_locator = page.get_by_role("button", name="Continue")
            if continue_locator.count() > 0:
                continue_locator.first.click()
                page.wait_for_load_state("domcontentloaded")
                advanced_to_next = True
            break

        result = QuizCaptureResult(
            mode=self.mode,
            question_text=question_text,
            options=options,
            selected_answer=selected_answer,
            feedback_text=feedback_text,
            question_screenshot_uri=question_screenshot_uri,
            feedback_screenshot_uri=feedback_screenshot_uri,
            attempts_used=attempts_used,
            advanced_to_next=advanced_to_next,
            stopped_reason=None if advanced_to_next else "quiz_not_advanced",
        )
        self.history.append(result)
        return result
