from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.page_classifier import FixtureHtmlExtractor, classify_fixture_page
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
from som_seedtalent_capture.permissions import AuthorizationDecision, PermissionManifest, authorize_capture


class DiscoveredCourseCard(BaseModel):
    course_title: str
    vendor: str | None = None
    summary: str | None = None
    relative_href: str
    link_text: str | None = None


class CourseInventoryItem(BaseModel):
    course_title: str
    vendor: str | None = None
    source_url: str
    catalog_url: str
    screenshot_uri: str
    summary: str | None = None
    discovery_page_kind: PageKind
    authorization: AuthorizationDecision

    @property
    def authorized(self) -> bool:
        return self.authorization.authorized


class CourseDiscoveryResult(BaseModel):
    catalog_url: str
    screenshot_uri: str
    observation: PageObservation
    items: list[CourseInventoryItem] = Field(default_factory=list)


class _CourseCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_course_card = False
        self._section_depth = 0
        self._inside_heading = False
        self._inside_link = False
        self._inside_paragraph = False
        self._current_heading: list[str] = []
        self._current_link: list[str] = []
        self._current_paragraph: list[str] = []
        self._cards: list[DiscoveredCourseCard] = []
        self._card_state: dict[str, str | None] | None = None

    @property
    def cards(self) -> list[DiscoveredCourseCard]:
        return self._cards

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = (attr_map.get("class") or "").split()

        if tag == "section" and "course-card" in classes:
            self._inside_course_card = True
            self._section_depth = 1
            self._card_state = {
                "course_title": None,
                "vendor": None,
                "summary": None,
                "relative_href": None,
                "link_text": None,
            }
            return

        if not self._inside_course_card:
            return

        if tag == "section":
            self._section_depth += 1
        elif tag in {"h1", "h2", "h3"}:
            self._inside_heading = True
            self._current_heading = []
        elif tag == "a":
            self._inside_link = True
            self._current_link = []
            if self._card_state is not None:
                self._card_state["relative_href"] = attr_map.get("href")
        elif tag == "p":
            self._inside_paragraph = True
            self._current_paragraph = []

    def handle_endtag(self, tag: str) -> None:
        if not self._inside_course_card:
            return

        if tag == "section":
            self._section_depth -= 1
            if self._section_depth == 0 and self._card_state is not None:
                relative_href = self._card_state.get("relative_href")
                course_title = self._card_state.get("course_title")
                if relative_href and course_title:
                    self._cards.append(
                        DiscoveredCourseCard(
                            course_title=course_title,
                            vendor=self._card_state.get("vendor"),
                            summary=self._card_state.get("summary"),
                            relative_href=relative_href,
                            link_text=self._card_state.get("link_text"),
                        )
                    )
                self._inside_course_card = False
                self._card_state = None
        elif tag in {"h1", "h2", "h3"}:
            self._inside_heading = False
            if self._card_state is not None:
                heading = " ".join(self._current_heading).strip()
                if heading and self._card_state["course_title"] is None:
                    self._card_state["course_title"] = heading
        elif tag == "a":
            self._inside_link = False
            if self._card_state is not None:
                link_text = " ".join(self._current_link).strip()
                if link_text:
                    self._card_state["link_text"] = link_text
        elif tag == "p":
            self._inside_paragraph = False
            if self._card_state is not None:
                paragraph = " ".join(self._current_paragraph).strip()
                if not paragraph:
                    return
                if paragraph.lower().startswith("vendor:"):
                    self._card_state["vendor"] = paragraph.split(":", maxsplit=1)[1].strip()
                elif self._card_state["summary"] is None and not paragraph.endswith("course available"):
                    self._card_state["summary"] = paragraph

    def handle_data(self, data: str) -> None:
        if not self._inside_course_card:
            return

        cleaned = " ".join(data.split())
        if not cleaned:
            return

        if self._inside_heading:
            self._current_heading.append(cleaned)
        if self._inside_link:
            self._current_link.append(cleaned)
        if self._inside_paragraph:
            self._current_paragraph.append(cleaned)


def discover_fixture_courses(
    *,
    html_text: str,
    catalog_url: str,
    screenshot_uri: str,
    manifest: PermissionManifest,
) -> CourseDiscoveryResult:
    extractor = FixtureHtmlExtractor()
    snapshot = extractor.extract(html_text)
    observation = classify_fixture_page(url=catalog_url, snapshot=snapshot, screenshot_uri=screenshot_uri)

    if observation.page_kind not in {PageKind.CATALOG, PageKind.ASSIGNED_LEARNING}:
        raise ValueError("course discovery requires a catalog or assigned learning page")

    parser = _CourseCardParser()
    parser.feed(html_text)
    parser.close()

    items = [
        CourseInventoryItem(
            course_title=card.course_title,
            vendor=card.vendor,
            source_url=urljoin(catalog_url, card.relative_href),
            catalog_url=catalog_url,
            screenshot_uri=screenshot_uri,
            summary=card.summary,
            discovery_page_kind=observation.page_kind,
            authorization=authorize_capture(
                url=urljoin(catalog_url, card.relative_href),
                vendor=card.vendor,
                course_title=card.course_title,
                manifest=manifest,
            ),
        )
        for card in parser.cards
    ]

    return CourseDiscoveryResult(
        catalog_url=catalog_url,
        screenshot_uri=screenshot_uri,
        observation=observation,
        items=items,
    )


def discover_fixture_courses_from_file(
    *,
    path: str | Path,
    catalog_url: str,
    screenshot_uri: str,
    manifest: PermissionManifest,
) -> CourseDiscoveryResult:
    html_text = Path(path).read_text(encoding="utf-8")
    return discover_fixture_courses(
        html_text=html_text,
        catalog_url=catalog_url,
        screenshot_uri=screenshot_uri,
        manifest=manifest,
    )
