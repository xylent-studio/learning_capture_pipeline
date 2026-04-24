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
        self._text_chunks: list[str] = []
        self.buttons: list[str] = []
        self.links: list[str] = []
        self.media = MediaSummary()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)

        if tag == "body":
            self.data_page_kind = attr_map.get("data-page-kind")
        elif tag == "title":
            self._inside_title = True
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

        if self._inside_button:
            self._current_button_text.append(cleaned)
        if self._inside_link:
            self._current_link_text.append(cleaned)

    def to_snapshot(self) -> VisibleDomSnapshot:
        return VisibleDomSnapshot(
            title=self.title,
            data_page_kind=self.data_page_kind,
            visible_text=" ".join(self._text_chunks),
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
