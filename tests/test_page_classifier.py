from pathlib import Path

from som_seedtalent_capture.autopilot.page_classifier import FixtureHtmlExtractor, classify_fixture_page
from som_seedtalent_capture.autopilot.state_machine import PageKind


FIXTURE_ROOT = Path("tests/fixtures/fake_seedtalent")


def classify_fixture_page_from_file(name: str):
    extractor = FixtureHtmlExtractor()
    path = FIXTURE_ROOT / name
    snapshot = extractor.extract_file(path)
    return snapshot, classify_fixture_page(url=f"file:///{name}", snapshot=snapshot)


def test_extracts_visible_text_buttons_links_and_fixture_marker():
    snapshot, observation = classify_fixture_page_from_file("catalog.html")

    assert snapshot.title == "SeedTalent Fixture Catalog"
    assert snapshot.data_page_kind == "catalog"
    assert "Open Course" in snapshot.links
    assert "Assigned Learning Catalog" in snapshot.visible_text
    assert observation.page_kind == PageKind.CATALOG


def test_classify_course_overview_fixture():
    snapshot, observation = classify_fixture_page_from_file("course-overview.html")

    assert snapshot.data_page_kind == "course_overview"
    assert observation.page_kind == PageKind.COURSE_OVERVIEW
    assert "Start Course" in observation.buttons


def test_classify_lesson_list_fixture():
    _snapshot, observation = classify_fixture_page_from_file("lesson-list.html")

    assert observation.page_kind == PageKind.LESSON_LIST
    assert "Open Static Lesson" in observation.links


def test_classify_static_lesson_fixture():
    _snapshot, observation = classify_fixture_page_from_file("lesson-static.html")

    assert observation.page_kind == PageKind.LESSON_STATIC_TEXT
    assert "Next" in observation.buttons


def test_classify_video_lesson_fixture():
    _snapshot, observation = classify_fixture_page_from_file("lesson-video.html")

    assert observation.page_kind == PageKind.LESSON_VIDEO
    assert observation.media.count == 1
    assert "Play Lesson Video" in observation.buttons


def test_classify_audio_lesson_fixture():
    _snapshot, observation = classify_fixture_page_from_file("lesson-audio.html")

    assert observation.page_kind == PageKind.LESSON_AUDIO
    assert observation.media.count == 1
    assert "Play Lesson Audio" in observation.buttons


def test_classify_quiz_fixture():
    _snapshot, observation = classify_fixture_page_from_file("quiz.html")

    assert observation.page_kind == PageKind.QUIZ_QUESTION
    assert "Submit" in observation.buttons


def test_classify_feedback_fixture():
    _snapshot, observation = classify_fixture_page_from_file("feedback.html")

    assert observation.page_kind == PageKind.QUIZ_FEEDBACK
    assert "Continue" in observation.buttons


def test_classify_report_fixture():
    _snapshot, observation = classify_fixture_page_from_file("report.html")

    assert observation.page_kind == PageKind.REPORT_TABLE
    assert "Export CSV" in observation.buttons


def test_classify_completion_fixture():
    _snapshot, observation = classify_fixture_page_from_file("completion.html")

    assert observation.page_kind == PageKind.COMPLETION_PAGE
    assert "Back to Catalog" in observation.buttons
