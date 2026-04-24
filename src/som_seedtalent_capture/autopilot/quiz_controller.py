from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Page
from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import QuizCaptureMode
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation

_ALLOWED_RESULTS_CONTROLS = ["next", "continue", "finish", "complete", "return to catalog"]
_DISALLOWED_RESULTS_CONTROLS = ["take again", "skip to lesson"]
_STOPWORDS = {"the", "and", "or", "to", "of", "a", "an", "is", "are", "be", "for", "that", "this", "with", "all"}


class QuizEvidenceSnippet(BaseModel):
    source_reference: str
    text: str
    score: float = Field(default=0.0, ge=0.0)


class QuizCaptureResult(BaseModel):
    mode: QuizCaptureMode
    page_kind: PageKind
    question_text: str | None = None
    options: list[str] = Field(default_factory=list)
    selected_answers: list[str] = Field(default_factory=list)
    feedback_text: str | None = None
    score_text: str | None = None
    progression_controls: list[str] = Field(default_factory=list)
    question_screenshot_uri: str
    feedback_screenshot_uri: str | None = None
    attempts_used: int = Field(default=0, ge=0)
    attempt_number: int = Field(default=1, ge=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_references: list[str] = Field(default_factory=list)
    answer_strategy: str = "capture_only"
    feedback_changed_retry: bool = False
    advanced_to_next: bool = False
    applied_action_label: str | None = None
    stopped_reason: str | None = None


def _normalize_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", text.lower())
        if token and token not in _STOPWORDS and len(token) > 1
    }


def _capture_screenshot(page: Page, screenshot_dir: Path, name: str, timestamp_ms: int) -> str:
    screenshot_uri = str((screenshot_dir / f"{name}-{timestamp_ms}.png").resolve())
    page.screenshot(path=screenshot_uri, full_page=True)
    return screenshot_uri


def _visible_button_texts(surface: Any) -> list[str]:
    return [text.strip() for text in surface.locator("button:visible").all_inner_texts() if text.strip()]


def _visible_label_texts(surface: Any) -> list[str]:
    raw_texts = [text.strip() for text in surface.locator("label:visible").all_inner_texts() if text.strip()]
    seen: set[str] = set()
    labels: list[str] = []
    for text in raw_texts:
        if text not in seen:
            seen.add(text)
            labels.append(text)
    return labels


def _extract_question_text(body_text: str, headings: list[str], options: list[str]) -> str | None:
    candidate_lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    option_set = {option.strip() for option in options}

    for line in candidate_lines:
        lowered = line.lower()
        if line in option_set:
            continue
        if lowered in {"quiz results", "submit", "next", "take again"}:
            continue
        if lowered.startswith("question") and any(char.isdigit() for char in lowered):
            continue
        if "your score" in lowered or "passing" in lowered:
            continue
        if "?" in line:
            return line

    for heading in headings:
        if "quiz results" not in heading.lower() and not heading.lower().startswith("question"):
            return heading.strip()

    for line in candidate_lines:
        lowered = line.lower()
        if line in option_set:
            continue
        if lowered.startswith("question"):
            continue
        if len(line) > 20:
            return line
    return None


def _extract_score_text(body_text: str) -> str | None:
    lowered = body_text.lower()
    score_match = re.search(r"(your score\s+\d+%|score\s+\d+%)", lowered)
    if score_match:
        return score_match.group(1)
    if "passed" in lowered:
        return "passed"
    if "failed" in lowered:
        return "failed"
    return None


def _build_retry_feedback_map(feedback_text: str, options: list[str]) -> tuple[list[str], list[str]]:
    normalized = " ".join(feedback_text.split())
    correct: list[str] = []
    incorrect: list[str] = []
    for option in options:
        pattern = re.compile(re.escape(option) + r"\s+(Correctly checked|Incorrectly checked)", re.IGNORECASE)
        match = pattern.search(normalized)
        if not match:
            continue
        status = match.group(1).lower()
        if "incorrectly" in status:
            incorrect.append(option)
        else:
            correct.append(option)
    return correct, incorrect


def _score_options_against_evidence(question_text: str | None, options: list[str], snippets: list[QuizEvidenceSnippet]) -> tuple[list[str], float, list[str]]:
    if not options or not snippets:
        return [], 0.0, []

    question_tokens = _normalize_tokens(question_text or "")
    option_scores: list[tuple[str, float, list[str]]] = []
    for option in options:
        option_tokens = _normalize_tokens(option) | question_tokens
        if not option_tokens:
            option_scores.append((option, 0.0, []))
            continue

        best_score = 0.0
        supporting_refs: list[str] = []
        for snippet in snippets:
            snippet_tokens = _normalize_tokens(snippet.text)
            if not snippet_tokens:
                continue
            overlap = len(option_tokens & snippet_tokens) / len(option_tokens)
            if option.lower() in snippet.text.lower():
                overlap = max(overlap, 0.9)
            if overlap > best_score:
                best_score = overlap
                supporting_refs = [snippet.source_reference]
        option_scores.append((option, best_score, supporting_refs))

    option_scores.sort(key=lambda item: item[1], reverse=True)
    multi_select = "select all that apply" in (question_text or "").lower()
    selected: list[str] = []
    evidence_refs: list[str] = []

    if multi_select:
        selected = [option for option, score, _refs in option_scores if score >= 0.75]
        for option, score, refs in option_scores:
            if option in selected:
                evidence_refs.extend(refs)
        confidence = min((score for option, score, _refs in option_scores if option in selected), default=0.0)
    else:
        top_option, top_score, refs = option_scores[0]
        if top_score >= 0.75:
            selected = [top_option]
            evidence_refs.extend(refs)
        confidence = top_score

    return selected, confidence, list(dict.fromkeys(evidence_refs))


def _click_label_for_option(surface: Any, option_text: str) -> bool:
    pattern = re.compile(rf"^\s*{re.escape(option_text)}\s*$", re.IGNORECASE)
    label_locator = surface.locator("label:visible").filter(has_text=pattern).first
    if label_locator.count() > 0:
        label_locator.click(force=True)
        return True
    labelled_input = surface.get_by_label(pattern).first
    if labelled_input.count() > 0:
        labelled_input.click(force=True)
        return True
    return False


def _click_progression_control(surface: Any, page: Page, labels: list[str]) -> str | None:
    for label in labels:
        pattern = re.compile(label, re.IGNORECASE)
        button = surface.get_by_role("button", name=pattern).first
        if button.count() > 0:
            clicked = button.inner_text().strip()
            button.click()
            page.wait_for_timeout(750)
            return clicked
        visible = surface.locator("button:visible").filter(has_text=pattern).first
        if visible.count() > 0:
            clicked = visible.inner_text().strip()
            visible.click()
            page.wait_for_timeout(750)
            return clicked
    return None


class FixtureQuizController:
    def __init__(self, *, mode: QuizCaptureMode = QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT, max_attempts: int = 2) -> None:
        self.mode = mode
        self.max_attempts = max_attempts
        self.history: list[QuizCaptureResult] = []

    @property
    def last_result(self) -> QuizCaptureResult | None:
        return self.history[-1] if self.history else None

    def run(
        self,
        *,
        page: Page,
        observation: PageObservation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
    ) -> QuizCaptureResult:
        del logical_url
        body_text = page.locator("main").inner_text().strip()
        headings = [text.strip() for text in page.locator("h1:visible, h2:visible, h3:visible").all_inner_texts() if text.strip()]
        options = _visible_label_texts(page)
        controls = _visible_button_texts(page)
        question_text = _extract_question_text(body_text, headings, options)
        question_screenshot_uri = _capture_screenshot(page, screenshot_dir, "quiz-question", timestamp_ms)

        if self.mode == QuizCaptureMode.CAPTURE_ONLY:
            result = QuizCaptureResult(
                mode=self.mode,
                page_kind=observation.page_kind,
                question_text=question_text,
                options=options,
                question_screenshot_uri=question_screenshot_uri,
                progression_controls=controls,
                answer_strategy="capture_only",
                stopped_reason="capture_only_mode",
            )
            self.history.append(result)
            return result

        if self.mode == QuizCaptureMode.MODEL_ASSISTED_ANSWER:
            result = QuizCaptureResult(
                mode=self.mode,
                page_kind=observation.page_kind,
                question_text=question_text,
                options=options,
                question_screenshot_uri=question_screenshot_uri,
                progression_controls=controls,
                answer_strategy="model_assisted_stub",
                stopped_reason="model_assisted_answer_not_implemented",
            )
            self.history.append(result)
            return result

        selected_answers = options[:1] if options else []
        for answer in selected_answers:
            _click_label_for_option(page, answer)
        clicked = _click_progression_control(page, page, ["submit"])
        page.wait_for_timeout(500)
        feedback_text = page.locator("main").inner_text().strip()
        feedback_screenshot_uri = _capture_screenshot(page, screenshot_dir, "quiz-feedback", timestamp_ms)
        next_clicked = _click_progression_control(page, page, ["continue", "next"])

        result = QuizCaptureResult(
            mode=self.mode,
            page_kind=observation.page_kind,
            question_text=question_text,
            options=options,
            selected_answers=selected_answers,
            feedback_text=feedback_text,
            score_text=_extract_score_text(feedback_text),
            progression_controls=_visible_button_texts(page),
            question_screenshot_uri=question_screenshot_uri,
            feedback_screenshot_uri=feedback_screenshot_uri,
            attempts_used=1,
            attempt_number=len(self.history) + 1,
            confidence=0.2 if selected_answers else 0.0,
            answer_strategy="fallback_first_option",
            advanced_to_next=next_clicked is not None,
            applied_action_label=next_clicked or clicked,
            stopped_reason=None if next_clicked is not None else "quiz_not_advanced",
        )
        self.history.append(result)
        return result


class LiveQuizController:
    def __init__(self, *, mode: QuizCaptureMode, max_attempts: int = 2, evidence_threshold: float = 0.75) -> None:
        self.mode = mode
        self.max_attempts = max_attempts
        self.evidence_threshold = evidence_threshold
        self.history: list[QuizCaptureResult] = []
        self._question_attempts: dict[str, int] = {}

    def run(
        self,
        *,
        page: Page,
        surface: Any,
        observation: PageObservation,
        screenshot_dir: Path,
        logical_url: str | None,
        timestamp_ms: int,
        evidence_snippets: list[QuizEvidenceSnippet],
    ) -> QuizCaptureResult:
        del logical_url
        body_text = surface.locator("body").inner_text().strip()
        headings = [text.strip() for text in surface.locator("h1:visible, h2:visible, h3:visible").all_inner_texts() if text.strip()]
        options = _visible_label_texts(surface)
        controls = _visible_button_texts(surface)
        question_text = _extract_question_text(body_text, headings, options)
        question_key = question_text or observation.url
        attempt_number = self._question_attempts.get(question_key, 0) + (1 if observation.page_kind == PageKind.QUIZ_QUESTION else 0)
        question_screenshot_uri = _capture_screenshot(page, screenshot_dir, "quiz-state", timestamp_ms)

        if observation.page_kind == PageKind.QUIZ_INTRO:
            clicked = _click_progression_control(surface, page, ["start quiz", "^start$", "begin quiz"])
            result = QuizCaptureResult(
                mode=self.mode,
                page_kind=observation.page_kind,
                question_text=question_text,
                options=options,
                progression_controls=controls,
                question_screenshot_uri=question_screenshot_uri,
                attempt_number=max(attempt_number, 1),
                answer_strategy="quiz_intro_start",
                applied_action_label=clicked,
                advanced_to_next=clicked is not None,
                stopped_reason=None if clicked is not None else "quiz_intro_not_started",
            )
            self.history.append(result)
            return result

        if observation.page_kind == PageKind.QUIZ_RESULTS:
            feedback_screenshot_uri = _capture_screenshot(page, screenshot_dir, "quiz-results", timestamp_ms)
            clicked = _click_progression_control(surface, page, [rf"^{label}$" for label in _ALLOWED_RESULTS_CONTROLS])
            feedback_changed_retry = False
            if clicked is None:
                can_retry = self.mode != QuizCaptureMode.CAPTURE_ONLY and self._question_attempts.get(question_key, 0) < self.max_attempts
                take_again_available = any(control.lower() == "take again" for control in controls)
                if can_retry and take_again_available:
                    clicked = _click_progression_control(surface, page, ["take again"])
                    feedback_changed_retry = clicked is not None

            result = QuizCaptureResult(
                mode=self.mode,
                page_kind=observation.page_kind,
                question_text=question_text,
                options=options,
                feedback_text=body_text,
                score_text=_extract_score_text(body_text),
                progression_controls=controls,
                question_screenshot_uri=question_screenshot_uri,
                feedback_screenshot_uri=feedback_screenshot_uri,
                attempts_used=self._question_attempts.get(question_key, 0),
                attempt_number=max(self._question_attempts.get(question_key, 0), 1),
                answer_strategy="results_exit",
                feedback_changed_retry=feedback_changed_retry,
                advanced_to_next=clicked is not None and clicked.lower() not in _DISALLOWED_RESULTS_CONTROLS,
                applied_action_label=clicked,
                stopped_reason=None if clicked is not None else "quiz_results_not_advanced",
            )
            self.history.append(result)
            return result

        if self.mode == QuizCaptureMode.CAPTURE_ONLY:
            result = QuizCaptureResult(
                mode=self.mode,
                page_kind=observation.page_kind,
                question_text=question_text,
                options=options,
                progression_controls=controls,
                question_screenshot_uri=question_screenshot_uri,
                attempt_number=max(attempt_number, 1),
                answer_strategy="capture_only",
                stopped_reason="capture_only_mode",
            )
            self.history.append(result)
            return result

        selected_answers, confidence, evidence_refs = _score_options_against_evidence(question_text, options, evidence_snippets)
        answer_strategy = "evidence_grounded" if selected_answers and confidence >= self.evidence_threshold else "fallback_selection"
        if not selected_answers:
            prior_feedback = next((item.feedback_text for item in reversed(self.history) if item.feedback_text), None)
            if prior_feedback:
                correct, incorrect = _build_retry_feedback_map(prior_feedback, options)
                selected_answers = [option for option in correct if option not in incorrect]
                if selected_answers:
                    answer_strategy = "feedback_informed_retry"
                    confidence = max(confidence, 0.8)
            if not selected_answers and options:
                selected_answers = [options[0]]

        applied_any = False
        for answer in selected_answers:
            applied_any = _click_label_for_option(surface, answer) or applied_any

        clicked_submit = _click_progression_control(surface, page, ["submit"])
        self._question_attempts[question_key] = attempt_number
        feedback_text = surface.locator("body").inner_text().strip()
        feedback_screenshot_uri = None
        score_text = _extract_score_text(feedback_text)
        if score_text or "correctly checked" in feedback_text.lower() or "incorrectly checked" in feedback_text.lower():
            feedback_screenshot_uri = _capture_screenshot(page, screenshot_dir, "quiz-feedback", timestamp_ms)

        result = QuizCaptureResult(
            mode=self.mode,
            page_kind=observation.page_kind,
            question_text=question_text,
            options=options,
            selected_answers=selected_answers,
            feedback_text=feedback_text if feedback_screenshot_uri else None,
            score_text=score_text,
            progression_controls=_visible_button_texts(surface),
            question_screenshot_uri=question_screenshot_uri,
            feedback_screenshot_uri=feedback_screenshot_uri,
            attempts_used=attempt_number,
            attempt_number=attempt_number,
            confidence=confidence,
            evidence_references=evidence_refs,
            answer_strategy=answer_strategy,
            applied_action_label=clicked_submit if applied_any else None,
            stopped_reason=None if clicked_submit is not None else "quiz_question_not_submitted",
        )
        self.history.append(result)
        return result
