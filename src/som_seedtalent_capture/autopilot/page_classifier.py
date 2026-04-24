from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.state_machine import MediaSummary, PageKind, PageObservation


class VisibleDomSnapshot(BaseModel):
    title: str | None = None
    data_page_kind: str | None = None
    visible_text: str = ""
    headings: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    media: MediaSummary = Field(default_factory=MediaSummary)


class VisibleDomExtractor(Protocol):
    def extract(self, html_text: str) -> VisibleDomSnapshot:
        ...


class _FixtureHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.data_page_kind: str | None = None
        self._inside_title = False
        self._inside_button = False
        self._inside_link = False
        self._current_button_text: list[str] = []
        self._current_link_text: list[str] = []
        self._inside_heading = False
        self._current_heading_text: list[str] = []
        self._text_chunks: list[str] = []
        self.headings: list[str] = []
        self.buttons: list[str] = []
        self.links: list[str] = []
        self.media = MediaSummary()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)

        if tag == "body":
            self.data_page_kind = attr_map.get("data-page-kind")
        elif tag == "title":
            self._inside_title = True
        elif tag in {"h1", "h2", "h3"}:
            self._inside_heading = True
            self._current_heading_text = []
        elif tag == "button":
            self._inside_button = True
            self._current_button_text = []
        elif tag == "a":
            self._inside_link = True
            self._current_link_text = []
        elif tag == "video":
            self.media.count += 1
        elif tag == "audio":
            self.media.count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False
        elif tag in {"h1", "h2", "h3"}:
            self._inside_heading = False
            heading_text = " ".join(self._current_heading_text).strip()
            if heading_text:
                self.headings.append(heading_text)
        elif tag == "button":
            self._inside_button = False
            button_text = " ".join(self._current_button_text).strip()
            if button_text:
                self.buttons.append(button_text)
        elif tag == "a":
            self._inside_link = False
            link_text = " ".join(self._current_link_text).strip()
            if link_text:
                self.links.append(link_text)

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return

        if self._inside_title:
            self.title = cleaned

        self._text_chunks.append(cleaned)

        if self._inside_heading:
            self._current_heading_text.append(cleaned)
        if self._inside_button:
            self._current_button_text.append(cleaned)
        if self._inside_link:
            self._current_link_text.append(cleaned)

    def to_snapshot(self) -> VisibleDomSnapshot:
        return VisibleDomSnapshot(
            title=self.title,
            data_page_kind=self.data_page_kind,
            visible_text=" ".join(self._text_chunks),
            headings=self.headings,
            buttons=self.buttons,
            links=self.links,
            media=self.media,
        )


class FixtureHtmlExtractor:
    def extract(self, html_text: str) -> VisibleDomSnapshot:
        parser = _FixtureHtmlParser()
        parser.feed(html_text)
        parser.close()
        return parser.to_snapshot()

    def extract_file(self, path: str | Path) -> VisibleDomSnapshot:
        return self.extract(Path(path).read_text(encoding="utf-8"))


_FIXTURE_PAGE_KIND_MAP = {
    "catalog": PageKind.CATALOG,
    "course_overview": PageKind.COURSE_OVERVIEW,
    "lesson_list": PageKind.LESSON_LIST,
    "lesson_static_text": PageKind.LESSON_STATIC_TEXT,
    "lesson_video": PageKind.LESSON_VIDEO,
    "lesson_audio": PageKind.LESSON_AUDIO,
    "quiz_question": PageKind.QUIZ_QUESTION,
    "quiz_feedback": PageKind.QUIZ_FEEDBACK,
    "completion_page": PageKind.COMPLETION_PAGE,
    "report_table": PageKind.REPORT_TABLE,
}


def _classify_by_visible_signals(snapshot: VisibleDomSnapshot) -> tuple[PageKind, float]:
    haystack = " ".join(
        [
            snapshot.title or "",
            " ".join(snapshot.headings),
            snapshot.visible_text,
            " ".join(snapshot.buttons),
            " ".join(snapshot.links),
        ]
    ).lower()

    if "assigned learning catalog" in haystack or "open course" in haystack:
        return PageKind.CATALOG, 0.95

    if "course overview" in haystack or "start course" in haystack:
        return PageKind.COURSE_OVERVIEW, 0.92

    if "lesson list" in haystack and "open static lesson" in haystack:
        return PageKind.LESSON_LIST, 0.95

    if "static lesson" in haystack or "store entry checklist" in haystack:
        return PageKind.LESSON_STATIC_TEXT, 0.9

    if "video lesson" in haystack or "play lesson video" in haystack:
        return PageKind.LESSON_VIDEO, 0.93

    if "audio lesson" in haystack or "play lesson audio" in haystack:
        return PageKind.LESSON_AUDIO, 0.93

    if ("knowledge check" in haystack or "safety quiz" in haystack) and "submit" in haystack:
        return PageKind.QUIZ_QUESTION, 0.94

    if "quiz feedback" in haystack or ("correct" in haystack and "continue" in haystack):
        return PageKind.QUIZ_FEEDBACK, 0.94

    if "course completion report" in haystack or "export csv" in haystack:
        return PageKind.REPORT_TABLE, 0.9

    if "completed" in haystack and "return to catalog" in haystack:
        return PageKind.COMPLETION_PAGE, 0.95

    return PageKind.UNKNOWN, 0.2


def classify_visible_page(
    *,
    url: str,
    snapshot: VisibleDomSnapshot,
    screenshot_uri: str | None = None,
) -> PageObservation:
    haystack = " ".join(
        [
            snapshot.title or "",
            " ".join(snapshot.headings),
            snapshot.visible_text,
            " ".join(snapshot.buttons),
            " ".join(snapshot.links),
        ]
    ).lower()
    visible_buttons = {button.strip().lower() for button in snapshot.buttons if button.strip()}
    has_results_signal = any(token in haystack for token in {"quiz results", "your score", "you scored", "score:"})
    has_question_signal = any(token in haystack for token in {"question", "select all that apply", "knowledge check", "assessment"})
    has_submit_button = "submit" in visible_buttons or "submit" in haystack
    has_results_progression = any(control in visible_buttons for control in {"continue", "finish", "complete", "return to catalog"})

    if any(token in haystack for token in {"sign in", "log in", "login", "session expired"}):
        page_kind, confidence = PageKind.AUTH_REQUIRED, 0.96
    elif "dashboard" in haystack and any(token in haystack for token in {"course library", "reports", "logout"}) and not any(
        token in haystack for token in {"lesson", "quiz", "course overview", "start course"}
    ):
        page_kind, confidence = PageKind.COURSE_SHELL_LOADING, 0.82
    elif any(token in haystack for token in {"loading", "please wait", "launching course", "preparing course"}) and "dashboard" not in haystack:
        page_kind, confidence = PageKind.SCORM_FRAME_LOADING, 0.84
    elif any(token in haystack for token in {"read and select each box to move on", "complete the content above before moving on"}):
        page_kind, confidence = PageKind.LESSON_INTERACTION_GATE, 0.91
    elif has_question_signal and has_submit_button and has_results_signal and not has_results_progression:
        page_kind, confidence = PageKind.QUIZ_QUESTION, 0.95
    elif has_results_signal and any(token in haystack for token in {"next", "take again", "continue"}):
        page_kind, confidence = PageKind.QUIZ_RESULTS, 0.94
    elif any(token in haystack for token in {"start quiz", "begin quiz"}) and not any(
        token in haystack for token in {"question", "submit", "quiz results"}
    ):
        page_kind, confidence = PageKind.QUIZ_INTRO, 0.9
    elif "submit" in haystack and (any(token in haystack for token in {"quiz", "question", "knowledge check", "assessment"}) or "/quiz/" in url):
        page_kind, confidence = PageKind.QUIZ_QUESTION, 0.9
    elif "by the end of this course" in haystack or ("lessons must be completed in order" in haystack and "start" in haystack):
        page_kind, confidence = PageKind.COURSE_OVERVIEW, 0.88
    elif any(token in haystack for token in {"skip to lesson", "lesson 1 of", "% complete"}) and any(
        token in haystack for token in {"continue", "home", "lesson"}
    ):
        page_kind, confidence = PageKind.LESSON_LIST, 0.85
    elif "assigned learning" in haystack:
        page_kind, confidence = PageKind.ASSIGNED_LEARNING, 0.92
    elif "catalog" in haystack and ("course" in haystack or snapshot.links):
        page_kind, confidence = PageKind.CATALOG, 0.85
    elif any(token in haystack for token in {"course overview", "start course", "begin course", "resume course"}):
        page_kind, confidence = PageKind.COURSE_OVERVIEW, 0.85
    elif any(token in haystack for token in {"lesson list", "curriculum", "lessons"}) and len(snapshot.links) >= 1:
        page_kind, confidence = PageKind.LESSON_LIST, 0.8
    elif snapshot.media.count > 0 and any("audio" in token.lower() for token in [snapshot.title or "", *snapshot.headings, *snapshot.buttons]):
        page_kind, confidence = PageKind.LESSON_AUDIO, 0.82
    elif snapshot.media.count > 0 or any("video" in token.lower() for token in [snapshot.title or "", *snapshot.headings, *snapshot.buttons]):
        page_kind, confidence = PageKind.LESSON_VIDEO, 0.82
    elif any(token in haystack for token in {"correct", "incorrect", "feedback"}) and "continue" in haystack:
        page_kind, confidence = PageKind.QUIZ_FEEDBACK, 0.8
    elif any(token in haystack for token in {"completion", "completed", "certificate"}):
        page_kind, confidence = PageKind.COMPLETION_PAGE, 0.88
    elif any(token in haystack for token in {"report", "export csv", "export", "completion report"}):
        page_kind, confidence = PageKind.REPORT_TABLE, 0.8
    elif any(token in haystack for token in {"next", "continue", "lesson", "module"}):
        page_kind, confidence = PageKind.LESSON_STATIC_TEXT, 0.62
    else:
        page_kind, confidence = PageKind.UNKNOWN, 0.2

    return PageObservation(
        url=url,
        title=snapshot.title,
        page_kind=page_kind,
        visible_text_sample=snapshot.visible_text[:300],
        buttons=snapshot.buttons,
        links=snapshot.links,
        media=snapshot.media,
        screenshot_uri=screenshot_uri,
        confidence=confidence,
    )


def classify_fixture_page(
    *,
    url: str,
    snapshot: VisibleDomSnapshot,
    screenshot_uri: str | None = None,
) -> PageObservation:
    if snapshot.data_page_kind in _FIXTURE_PAGE_KIND_MAP:
        page_kind = _FIXTURE_PAGE_KIND_MAP[snapshot.data_page_kind]
        confidence = 0.99
    else:
        page_kind, confidence = _classify_by_visible_signals(snapshot)

    return PageObservation(
        url=url,
        title=snapshot.title,
        page_kind=page_kind,
        visible_text_sample=snapshot.visible_text[:300],
        buttons=snapshot.buttons,
        links=snapshot.links,
        media=snapshot.media,
        screenshot_uri=screenshot_uri,
        confidence=confidence,
    )
