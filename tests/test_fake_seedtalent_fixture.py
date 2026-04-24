from pathlib import Path


FIXTURE_ROOT = Path("tests/fixtures/fake_seedtalent")


def test_fake_seedtalent_fixture_contains_expected_pages():
    expected_pages = {
        "catalog.html",
        "course-overview.html",
        "lesson-list.html",
        "lesson-static.html",
        "lesson-video.html",
        "lesson-audio.html",
        "quiz.html",
        "feedback.html",
        "report.html",
        "completion.html",
        "styles.css",
    }

    actual_pages = {path.name for path in FIXTURE_ROOT.iterdir()}

    assert expected_pages <= actual_pages


def test_fake_seedtalent_fixture_uses_dummy_training_text_only():
    catalog_html = (FIXTURE_ROOT / "catalog.html").read_text(encoding="utf-8")
    completion_html = (FIXTURE_ROOT / "completion.html").read_text(encoding="utf-8")
    report_html = (FIXTURE_ROOT / "report.html").read_text(encoding="utf-8")

    assert "Dummy training text for fixture use only" in catalog_html
    assert "fixture use only" in completion_html
    assert "Person A" in report_html
    assert "SeedTalent Fixture Catalog" in catalog_html


def test_fake_seedtalent_fixture_exposes_navigation_for_flow_testing():
    lesson_list_html = (FIXTURE_ROOT / "lesson-list.html").read_text(encoding="utf-8")
    quiz_html = (FIXTURE_ROOT / "quiz.html").read_text(encoding="utf-8")
    video_html = (FIXTURE_ROOT / "lesson-video.html").read_text(encoding="utf-8")

    assert 'href="lesson-static.html"' in lesson_list_html
    assert 'href="lesson-video.html"' in lesson_list_html
    assert 'href="lesson-audio.html"' in lesson_list_html
    assert 'href="report.html"' in lesson_list_html
    assert "Submit" in quiz_html
    assert "Play Lesson Video" in video_html
