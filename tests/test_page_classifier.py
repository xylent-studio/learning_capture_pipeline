from pathlib import Path

from som_seedtalent_capture.autopilot.page_classifier import VisibleDomSnapshot, FixtureHtmlExtractor, classify_fixture_page, classify_visible_page
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


def test_classify_live_scorm_course_overview():
    snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text=(
            "Seed & Strain | NY START Introducing the high-quality, value-driven cannabis Seed & Strain. "
            "By the end of this course, you will be able to identify the target consumers. "
            "Who is Seed & Strain? Flower This lesson is currently unavailable Lessons must be completed in order"
        ),
        links=["START", "Who is Seed & Strain?"],
    )

    observation = classify_visible_page(
        url="https://cdn.example/scormcontent/index.html#/preview",
        snapshot=snapshot,
    )

    assert observation.page_kind == PageKind.COURSE_OVERVIEW


def test_classify_live_scorm_lesson_list():
    snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text=(
            "SKIP TO LESSON Seed & Strain | NY 0% COMPLETE Home Who is Seed & Strain? "
            "LESSON 1 OF 4 CONTINUE 20% Completed Lessons must be completed in order"
        ),
        buttons=["SKIP TO LESSON", "CONTINUE"],
        links=["Seed & Strain | NY", "Who is Seed & Strain?", "Home"],
    )

    observation = classify_visible_page(
        url="https://cdn.example/scormcontent/index.html#/lessons/example",
        snapshot=snapshot,
    )

    assert observation.page_kind == PageKind.LESSON_LIST


def test_classify_live_scorm_checkbox_gate_as_static_lesson():
    snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text=(
            "Read and select each box to move on. "
            "Seed & Strain strives to bring unique and exciting strains to the market. "
            "Complete the content above before moving on."
        ),
    )

    observation = classify_visible_page(
        url="https://cdn.example/scormcontent/index.html#/lessons/example",
        snapshot=snapshot,
    )

    assert observation.page_kind == PageKind.LESSON_INTERACTION_GATE


def test_classify_live_submit_page_as_quiz_question():
    snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text="The highest THC % Submit",
        buttons=["Submit"],
    )

    observation = classify_visible_page(
        url="https://cdn.example/scormcontent/index.html#/quiz/example",
        snapshot=snapshot,
    )

    assert observation.page_kind == PageKind.QUIZ_QUESTION


def test_classify_live_quiz_intro():
    snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text="Knowledge Check Start Quiz",
        buttons=["Start Quiz"],
    )

    observation = classify_visible_page(
        url="https://cdn.example/scormcontent/index.html#/quiz/example",
        snapshot=snapshot,
    )

    assert observation.page_kind == PageKind.QUIZ_INTRO


def test_classify_live_quiz_results():
    snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text="Quiz Results You scored 50% and did not pass. Next Take Again",
        buttons=["NEXT", "TAKE AGAIN"],
        headings=["Quiz Results"],
    )

    observation = classify_visible_page(
        url="https://cdn.example/scormcontent/index.html#/quiz/example",
        snapshot=snapshot,
    )

    assert observation.page_kind == PageKind.QUIZ_RESULTS


def test_classify_live_mixed_quiz_state_as_question_when_submit_is_visible():
    snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text=(
            "Question 01/02 What is important to the Seed & Strain Growers? (select all that apply) "
            "Submit Next Quiz Results Your score 0% Failed Take Again"
        ),
        buttons=["SUBMIT", "NEXT", "TAKE AGAIN"],
        headings=["Quiz", "Question 01/02", "Quiz Results"],
    )

    observation = classify_visible_page(
        url="https://cdn.example/scormcontent/index.html#/quiz/example",
        snapshot=snapshot,
    )

    assert observation.page_kind == PageKind.QUIZ_QUESTION


def test_classify_shell_loading_vs_scorm_loading():
    shell_snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text="Dashboard Course Library Reports Logout",
    )
    frame_snapshot = VisibleDomSnapshot(
        title="Seed Talent",
        visible_text="Launching course please wait",
    )

    shell_observation = classify_visible_page(
        url="https://app.seedtalent.com/catalog",
        snapshot=shell_snapshot,
    )
    frame_observation = classify_visible_page(
        url="https://cdn.example/scormcontent/index.html#/loading",
        snapshot=frame_snapshot,
    )

    assert shell_observation.page_kind == PageKind.COURSE_SHELL_LOADING
    assert frame_observation.page_kind == PageKind.SCORM_FRAME_LOADING
