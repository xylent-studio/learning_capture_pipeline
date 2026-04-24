from pathlib import Path

import pytest

from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.state_machine import PageKind
from som_seedtalent_capture.permissions import load_permission_manifest


FIXTURE_ROOT = Path("tests/fixtures/fake_seedtalent")
MANIFEST_PATH = Path("config/permission_manifest.example.yaml")


def test_discover_fixture_course_inventory_item_is_authorized():
    result = discover_fixture_courses_from_file(
        path=FIXTURE_ROOT / "catalog.html",
        catalog_url="https://app.seedtalent.com/catalog.html",
        screenshot_uri="artifacts/screenshots/catalog.png",
        manifest=load_permission_manifest(MANIFEST_PATH),
    )

    assert result.observation.page_kind == PageKind.CATALOG
    assert result.screenshot_uri == "artifacts/screenshots/catalog.png"
    assert len(result.items) == 1

    item = result.items[0]
    assert item.course_title == "Retail Safety Basics"
    assert item.vendor == "Wildflower Learning Labs"
    assert item.source_url == "https://app.seedtalent.com/course-overview.html"
    assert item.discovery_page_kind == PageKind.CATALOG
    assert item.screenshot_uri == "artifacts/screenshots/catalog.png"
    assert item.authorized is True
    assert item.authorization.reason == "covered_by_permission_manifest"


def test_discovery_requires_catalog_page():
    with pytest.raises(ValueError, match="course discovery requires a catalog or assigned learning page"):
        discover_fixture_courses_from_file(
            path=FIXTURE_ROOT / "course-overview.html",
            catalog_url="https://app.seedtalent.com/course-overview.html",
            screenshot_uri="artifacts/screenshots/course-overview.png",
            manifest=load_permission_manifest(MANIFEST_PATH),
        )
