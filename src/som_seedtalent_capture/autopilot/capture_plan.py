from __future__ import annotations

from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.course_discovery import CourseInventoryItem
from som_seedtalent_capture.autopilot.page_classifier import FixtureHtmlExtractor, classify_fixture_page
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
from som_seedtalent_capture.models import RightsStatus


class RecorderProfile(StrEnum):
    FIXTURE_NOOP = "fixture_noop"
    HEADED_BROWSER_FFMPEG = "headed_browser_ffmpeg"
    HEADED_BROWSER_OBS = "headed_browser_obs"


class QuizCaptureMode(StrEnum):
    CAPTURE_ONLY = "capture_only"
    CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT = "capture_and_complete_on_capture_account"
    MODEL_ASSISTED_ANSWER = "model_assisted_answer"


class QaThresholds(BaseModel):
    min_page_observations: int = Field(default=1, ge=1)
    min_screenshot_count: int = Field(default=1, ge=1)
    min_classifier_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    require_quiz_capture: bool = True
    require_completion_capture: bool = True


class CapturePlan(BaseModel):
    course_title: str
    source_url: str
    permission_basis: str
    rights_status: RightsStatus
    screenshot_interval_seconds: int = Field(ge=1)
    recorder_profile: RecorderProfile
    quiz_mode: QuizCaptureMode
    max_course_duration_minutes: int = Field(ge=1)
    expected_lesson_count: int | None = Field(default=None, ge=1)
    lesson_list_url: str | None = None
    lesson_urls: list[str] = Field(default_factory=list)
    lesson_list_observation: PageObservation | None = None
    qa_thresholds: QaThresholds


class _LessonListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_lesson_card = False
        self._section_depth = 0
        self._inside_link = False
        self._current_link_text: list[str] = []
        self.lesson_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = (attr_map.get("class") or "").split()

        if tag == "section" and "lesson-card" in classes:
            self._inside_lesson_card = True
            self._section_depth = 1
            return

        if not self._inside_lesson_card:
            return

        if tag == "section":
            self._section_depth += 1
        elif tag == "a":
            self._inside_link = True
            self._current_link_text = []
            href = attr_map.get("href")
            if href:
                self.lesson_hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if not self._inside_lesson_card:
            return

        if tag == "section":
            self._section_depth -= 1
            if self._section_depth == 0:
                self._inside_lesson_card = False
        elif tag == "a":
            self._inside_link = False

    def handle_data(self, data: str) -> None:
        if not self._inside_link:
            return

        cleaned = " ".join(data.split())
        if cleaned:
            self._current_link_text.append(cleaned)


def build_fixture_capture_plan(
    *,
    inventory_item: CourseInventoryItem,
    lesson_list_html_text: str | None = None,
    lesson_list_url: str | None = None,
    screenshot_interval_seconds: int = 20,
    recorder_profile: RecorderProfile = RecorderProfile.FIXTURE_NOOP,
    quiz_mode: QuizCaptureMode = QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT,
    max_course_duration_minutes: int = 30,
) -> CapturePlan:
    expected_lesson_count: int | None = None
    lesson_urls: list[str] = []
    lesson_list_observation: PageObservation | None = None

    if lesson_list_html_text is not None:
        if lesson_list_url is None:
            raise ValueError("lesson_list_url is required when lesson_list_html_text is provided")

        extractor = FixtureHtmlExtractor()
        snapshot = extractor.extract(lesson_list_html_text)
        lesson_list_observation = classify_fixture_page(url=lesson_list_url, snapshot=snapshot)

        if lesson_list_observation.page_kind != PageKind.LESSON_LIST:
            raise ValueError("capture plan lesson list input must classify as lesson_list")

        parser = _LessonListParser()
        parser.feed(lesson_list_html_text)
        parser.close()

        lesson_urls = [urljoin(lesson_list_url, href) for href in parser.lesson_hrefs]
        expected_lesson_count = len(lesson_urls) or None

    qa_thresholds = QaThresholds(
        min_page_observations=max(expected_lesson_count or 1, 1),
        min_screenshot_count=max(expected_lesson_count or 1, 1),
        min_classifier_confidence=0.8,
        require_quiz_capture=True,
        require_completion_capture=True,
    )

    return CapturePlan(
        course_title=inventory_item.course_title,
        source_url=inventory_item.source_url,
        permission_basis=inventory_item.authorization.permission_basis,
        rights_status=inventory_item.authorization.rights_status,
        screenshot_interval_seconds=screenshot_interval_seconds,
        recorder_profile=recorder_profile,
        quiz_mode=quiz_mode,
        max_course_duration_minutes=max_course_duration_minutes,
        expected_lesson_count=expected_lesson_count,
        lesson_list_url=lesson_list_url,
        lesson_urls=lesson_urls,
        lesson_list_observation=lesson_list_observation,
        qa_thresholds=qa_thresholds,
    )


def build_fixture_capture_plan_from_file(
    *,
    inventory_item: CourseInventoryItem,
    path: str | Path,
    lesson_list_url: str,
    screenshot_interval_seconds: int = 20,
    recorder_profile: RecorderProfile = RecorderProfile.FIXTURE_NOOP,
    quiz_mode: QuizCaptureMode = QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT,
    max_course_duration_minutes: int = 30,
) -> CapturePlan:
    lesson_list_html_text = Path(path).read_text(encoding="utf-8")
    return build_fixture_capture_plan(
        inventory_item=inventory_item,
        lesson_list_html_text=lesson_list_html_text,
        lesson_list_url=lesson_list_url,
        screenshot_interval_seconds=screenshot_interval_seconds,
        recorder_profile=recorder_profile,
        quiz_mode=quiz_mode,
        max_course_duration_minutes=max_course_duration_minutes,
    )
