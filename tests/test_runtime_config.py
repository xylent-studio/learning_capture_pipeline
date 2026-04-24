from pathlib import Path

from som_seedtalent_capture.auth import AuthMode
from som_seedtalent_capture.config import (
    load_pilot_course_selection,
    load_runtime_pilot_config,
    validate_runtime_pilot_paths,
)


def test_load_runtime_pilot_config_and_validate_paths(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    secret_root = tmp_path / "secrets"
    artifact_root = tmp_path / "artifacts"
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        "\n".join(
            [
                "seedtalent_base_url: https://app.seedtalent.com",
                "account_alias: seedtalent-capture-bot",
                "auth_mode: manual_storage_state",
                "external_paths:",
                f"  secret_root: {secret_root}",
                f"  permission_manifest_path: {secret_root / 'manifests' / 'permission_manifest.yaml'}",
                f"  storage_state_path: {secret_root / 'playwright' / 'storage-state.json'}",
                f"  auth_screenshot_dir: {artifact_root / 'preflight'}",
                f"  artifact_root: {artifact_root}",
                f"  approved_courses_path: {secret_root / 'inputs' / 'approved_courses.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    config = load_runtime_pilot_config(config_path)
    validations = validate_runtime_pilot_paths(config, repo_root)

    assert config.auth_mode == AuthMode.MANUAL_STORAGE_STATE
    assert validations["secret_root_external"] is True
    assert validations["permission_manifest_under_secret_root"] is True
    assert validations["storage_state_under_secret_root"] is True
    assert validations["approved_courses_under_secret_root"] is True
    assert validations["artifact_root_external"] is True


def test_load_pilot_course_selection(tmp_path: Path):
    selection_path = tmp_path / "approved_courses.yaml"
    selection_path.write_text(
        "\n".join(
            [
                "account_alias: seedtalent-capture-bot",
                "courses:",
                "  - course_title: Approved Course",
                "    source_url: https://app.seedtalent.com/courses/approved-course",
                "    vendor: Approved Vendor",
                "    capture_priority: 1",
                "    estimated_duration_minutes: 25",
            ]
        ),
        encoding="utf-8",
    )

    selection = load_pilot_course_selection(selection_path)

    assert selection.account_alias == "seedtalent-capture-bot"
    assert len(selection.courses) == 1
    assert selection.courses[0].course_title == "Approved Course"
