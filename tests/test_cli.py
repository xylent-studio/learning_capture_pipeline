import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from som_seedtalent_capture.cli import app
from som_seedtalent_capture.auth import AuthMode, AuthPreflightResult, AuthPreflightStatus

runner = CliRunner()


def test_batch_create_writes_json(tmp_path: Path):
    out = tmp_path / "batch.json"
    result = runner.invoke(app, ["batch", "create", "--scope", "fake test scope", "--operator", "tester", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert "capture_batch_id" in out.read_text()


def test_session_note_writes_json(tmp_path: Path):
    out = tmp_path / "note.json"
    result = runner.invoke(app, [
        "session", "note",
        "--session-id", "session_fake",
        "--timestamp-ms", "1234",
        "--note", "Fake operator note",
        "--out", str(out),
    ])
    assert result.exit_code == 0
    assert out.exists()
    assert "Fake operator note" in out.read_text()


def _write_runtime_config(tmp_path: Path) -> Path:
    secret_root = tmp_path / "secrets"
    artifact_root = tmp_path / "artifacts"
    manifest_path = secret_root / "manifests" / "permission_manifest.yaml"
    storage_state_path = secret_root / "playwright" / "storage-state.json"
    approved_courses_path = secret_root / "inputs" / "approved_courses.yaml"

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    approved_courses_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_path.write_text(
        "\n".join(
            [
                "permission_manifest_id: cli-runtime",
                "contract_reference: cli-contract",
                "source_base_url: https://app.seedtalent.com",
                "allowed_course_patterns:",
                "  - '*'",
            ]
        ),
        encoding="utf-8",
    )
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")
    approved_courses_path.write_text(
        "\n".join(
            [
                "account_alias: seedtalent-capture-bot",
                "courses:",
                "  - course_title: Pilot Course",
                "    source_url: https://app.seedtalent.com/courses/pilot-course",
                "    vendor: Vendor A",
                "    estimated_duration_minutes: 30",
            ]
        ),
        encoding="utf-8",
    )

    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        "\n".join(
            [
                "seedtalent_base_url: https://app.seedtalent.com",
                "account_alias: seedtalent-capture-bot",
                "auth_mode: manual_storage_state",
                "external_paths:",
                f"  secret_root: {secret_root}",
                f"  permission_manifest_path: {manifest_path}",
                f"  storage_state_path: {storage_state_path}",
                f"  auth_screenshot_dir: {artifact_root / 'preflight'}",
                f"  artifact_root: {artifact_root}",
                f"  approved_courses_path: {approved_courses_path}",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def test_pilot_validate_config_writes_json(tmp_path: Path):
    config_path = _write_runtime_config(tmp_path)
    out = tmp_path / "runtime_validation.json"

    result = runner.invoke(app, ["pilot", "validate-config", "--config", str(config_path), "--out", str(out)])

    assert result.exit_code == 0
    assert out.exists()
    assert '"storage_state_under_secret_root": true' in out.read_text().lower()


def test_pilot_bootstrap_auth_creates_output(tmp_path: Path):
    config_path = _write_runtime_config(tmp_path)
    out = tmp_path / "bootstrap.json"

    result = runner.invoke(app, ["pilot", "bootstrap-auth", "--config", str(config_path), "--out", str(out)])

    assert result.exit_code == 0
    assert out.exists()
    assert "recommended_commands" in out.read_text()


def test_pilot_plans_from_approved_writes_bundle(tmp_path: Path):
    config_path = _write_runtime_config(tmp_path)
    out = tmp_path / "plans.json"

    result = runner.invoke(app, ["pilot", "plans-from-approved", "--config", str(config_path), "--out", str(out)])

    assert result.exit_code == 0
    assert out.exists()
    payload = out.read_text()
    assert '"metadata"' in payload
    assert '"plans"' in payload


def _write_plan_bundle(tmp_path: Path, config_path: Path) -> Path:
    out = tmp_path / "plans.json"
    result = runner.invoke(app, ["pilot", "plans-from-approved", "--config", str(config_path), "--out", str(out)])
    assert result.exit_code == 0
    return out


def test_scheduler_dry_run_writes_summary(tmp_path: Path):
    config_path = _write_runtime_config(tmp_path)
    out = tmp_path / "scheduler.json"

    result = runner.invoke(app, ["scheduler", "dry-run", "--config", str(config_path), "--out", str(out)])

    assert result.exit_code == 0
    assert out.exists()
    assert '"total_courses": 1' in out.read_text()


def test_pilot_run_course_writes_failure_bundle_when_auth_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = _write_runtime_config(tmp_path)
    plan_bundle_path = _write_plan_bundle(tmp_path, config_path)
    out = tmp_path / "run-summary.json"
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTH_EXPIRED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            account_alias=kwargs["account_alias"],
            current_url="https://app.seedtalent.com/login",
            error_reason="auth_expired",
        ),
    )

    result = runner.invoke(
        app,
        ["pilot", "run-course", "--config", str(config_path), "--plan-bundle", str(plan_bundle_path), "--out", str(out)],
    )

    assert result.exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "preflight_failed"
    assert payload["failure_bundle_path"] is not None


def test_pilot_run_course_respects_course_url_selection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = _write_runtime_config(tmp_path)
    plan_bundle_path = _write_plan_bundle(tmp_path, config_path)
    out = tmp_path / "run-summary.json"
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTHENTICATED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            account_alias=kwargs["account_alias"],
            current_url="https://app.seedtalent.com/catalog",
        ),
    )

    result = runner.invoke(
        app,
        [
            "pilot",
            "run-course",
            "--config",
            str(config_path),
            "--plan-bundle",
            str(plan_bundle_path),
            "--course-url",
            "https://app.seedtalent.com/courses/pilot-course",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "ready_for_live_capture"


def test_pilot_run_batch_blocks_all_runs_on_batch_preflight_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = _write_runtime_config(tmp_path)
    plan_bundle_path = _write_plan_bundle(tmp_path, config_path)
    out = tmp_path / "batch-summary.json"
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTH_EXPIRED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            current_url="https://app.seedtalent.com/login",
            error_reason="auth_expired",
        ),
    )

    result = runner.invoke(
        app,
        ["pilot", "run-batch", "--config", str(config_path), "--plan-bundle", str(plan_bundle_path), "--out", str(out)],
    )

    assert result.exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["batch_summary"]["status"] == "preflight_failed"
    assert payload["scheduler_summary"]["blocked_by_auth_count"] == 1


def test_pilot_run_batch_marks_runs_ready_for_live_capture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = _write_runtime_config(tmp_path)
    plan_bundle_path = _write_plan_bundle(tmp_path, config_path)
    out = tmp_path / "batch-summary.json"
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTHENTICATED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            current_url="https://app.seedtalent.com/catalog",
        ),
    )

    result = runner.invoke(
        app,
        ["pilot", "run-batch", "--config", str(config_path), "--plan-bundle", str(plan_bundle_path), "--out", str(out)],
    )

    assert result.exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["batch_summary"]["status"] == "ready_for_live_capture"
    assert payload["scheduler_summary"]["ready_for_live_capture_count"] == 1
