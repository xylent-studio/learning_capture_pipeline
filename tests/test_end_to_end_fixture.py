from pathlib import Path

import pytest
from playwright.sync_api import Error, sync_playwright

from som_seedtalent_capture.auth import AuthMode, BrowserPreflightObservation, FakeBrowserAuthPreflight, run_auth_preflight
from som_seedtalent_capture.autopilot.capture_plan import build_fixture_capture_plan_from_file
from som_seedtalent_capture.autopilot.course_discovery import discover_fixture_courses_from_file
from som_seedtalent_capture.autopilot.media_controller import FixtureMediaController
from som_seedtalent_capture.autopilot.qa import AutopilotReadinessStatus, evaluate_autopilot_run
from som_seedtalent_capture.autopilot.quiz_controller import FixtureQuizController
from som_seedtalent_capture.autopilot.recorder import FakeRecorderProvider
from som_seedtalent_capture.autopilot.runner import run_fixture_autopilot
from som_seedtalent_capture.permissions import load_permission_manifest


FIXTURE_ROOT = Path("tests/fixtures/fake_seedtalent")
MANIFEST_PATH = Path("config/permission_manifest.example.yaml")


def _ensure_chromium_or_skip() -> None:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Error as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"Playwright Chromium is not installed: {exc}")


def test_end_to_end_fixture_ready_for_reconstruction(tmp_path: Path):
    _ensure_chromium_or_skip()

    manifest = load_permission_manifest(MANIFEST_PATH)

    storage_state_path = tmp_path / "manual-storage-state.json"
    storage_state_path.write_text("{}", encoding="utf-8")
    auth_preflight = run_auth_preflight(
        mode=AuthMode.MANUAL_STORAGE_STATE,
        storage_state_path=storage_state_path,
        base_url=manifest.source_base_url,
        browser_preflight=FakeBrowserAuthPreflight(
            BrowserPreflightObservation(
                authenticated=True,
                current_url=f"{manifest.source_base_url}/catalog.html",
                visible_state_summary="Assigned learning catalog visible",
                screenshot_uri=str((tmp_path / "auth-preflight.png").resolve()),
            )
        ),
        repo_root=Path.cwd(),
        account_alias="seedtalent-capture-bot",
    )

    discovery = discover_fixture_courses_from_file(
        path=FIXTURE_ROOT / "catalog.html",
        catalog_url=f"{manifest.source_base_url}/catalog.html",
        screenshot_uri=str((tmp_path / "catalog.png").resolve()),
        manifest=manifest,
    )
    plan = build_fixture_capture_plan_from_file(
        inventory_item=discovery.items[0],
        path=FIXTURE_ROOT / "lesson-list.html",
        lesson_list_url=f"{manifest.source_base_url}/lesson-list.html",
    )

    run_result = run_fixture_autopilot(
        plan=plan,
        fixture_root=FIXTURE_ROOT,
        artifact_root=tmp_path / "artifacts",
        headless=True,
        media_controller=FixtureMediaController(mock_completion=True),
        quiz_controller=FixtureQuizController(),
        recorder_provider=FakeRecorderProvider(emit_audio_artifact=True),
    )
    qa_result = evaluate_autopilot_run(run_result=run_result, plan=plan)

    assert auth_preflight.authenticated is True
    assert discovery.items[0].authorized is True
    assert run_result.completion_detected is True
    assert qa_result.readiness_status == AutopilotReadinessStatus.READY_FOR_RECONSTRUCTION
    assert qa_result.recapture_reasons == []
