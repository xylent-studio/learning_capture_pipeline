from pathlib import Path

from som_seedtalent_capture.auth import (
    AuthMode,
    AuthPreflightStatus,
    BrowserPreflightObservation,
    FakeBrowserAuthPreflight,
    run_auth_preflight,
    validate_manual_storage_state_path,
)


def test_manual_storage_state_path_must_exist(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    missing_path = tmp_path / "missing" / "storage_state.json"

    status = validate_manual_storage_state_path(missing_path, repo_root)

    assert status == AuthPreflightStatus.FAILED


def test_manual_storage_state_path_cannot_live_inside_repo(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    storage_state_path = repo_root / ".secrets" / "storage_state.json"
    storage_state_path.parent.mkdir(parents=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")

    status = validate_manual_storage_state_path(storage_state_path, repo_root)

    assert status == AuthPreflightStatus.PROHIBITED_PATH


def test_manual_storage_state_path_can_live_outside_repo(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    storage_state_path = tmp_path / "outside-secrets" / "storage_state.json"
    storage_state_path.parent.mkdir(parents=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")

    status = validate_manual_storage_state_path(storage_state_path, repo_root)

    assert status is None


def test_run_auth_preflight_returns_authenticated_for_visible_logged_in_state(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    storage_state_path = tmp_path / "outside-secrets" / "storage_state.json"
    storage_state_path.parent.mkdir(parents=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")
    fake_preflight = FakeBrowserAuthPreflight(
        BrowserPreflightObservation(
            authenticated=True,
            current_url="https://app.seedtalent.com/dashboard",
            visible_state_summary="Dashboard visible",
            screenshot_uri="captures/preflight.png",
        )
    )

    result = run_auth_preflight(
        mode=AuthMode.MANUAL_STORAGE_STATE,
        storage_state_path=storage_state_path,
        base_url="https://app.seedtalent.com",
        browser_preflight=fake_preflight,
        repo_root=repo_root,
        account_alias="seedtalent-capture-bot",
    )

    assert result.status == AuthPreflightStatus.AUTHENTICATED
    assert result.authenticated is True
    assert result.account_alias == "seedtalent-capture-bot"
    assert result.screenshot_uri == "captures/preflight.png"


def test_run_auth_preflight_returns_auth_expired_when_browser_not_authenticated(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    storage_state_path = tmp_path / "outside-secrets" / "storage_state.json"
    storage_state_path.parent.mkdir(parents=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")
    fake_preflight = FakeBrowserAuthPreflight(
        BrowserPreflightObservation(
            authenticated=False,
            current_url="https://app.seedtalent.com/login",
            visible_state_summary="Login required",
        )
    )

    result = run_auth_preflight(
        mode=AuthMode.MANUAL_STORAGE_STATE,
        storage_state_path=storage_state_path,
        base_url="https://app.seedtalent.com",
        browser_preflight=fake_preflight,
        repo_root=repo_root,
    )

    assert result.status == AuthPreflightStatus.AUTH_EXPIRED
    assert result.error_reason == "auth_expired"


def test_run_auth_preflight_returns_prohibited_path_from_browser_observation(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    storage_state_path = tmp_path / "outside-secrets" / "storage_state.json"
    storage_state_path.parent.mkdir(parents=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")
    fake_preflight = FakeBrowserAuthPreflight(
        BrowserPreflightObservation(
            authenticated=True,
            current_url="https://app.seedtalent.com/settings",
            visible_state_summary="Settings page visible",
            prohibited_path_detected=True,
        )
    )

    result = run_auth_preflight(
        mode=AuthMode.MANUAL_STORAGE_STATE,
        storage_state_path=storage_state_path,
        base_url="https://app.seedtalent.com",
        browser_preflight=fake_preflight,
        repo_root=repo_root,
    )

    assert result.status == AuthPreflightStatus.PROHIBITED_PATH
    assert result.prohibited_path_detected is True


def test_run_auth_preflight_fails_for_unsupported_mode(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    storage_state_path = tmp_path / "outside-secrets" / "storage_state.json"
    storage_state_path.parent.mkdir(parents=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")
    fake_preflight = FakeBrowserAuthPreflight(
        BrowserPreflightObservation(
            authenticated=True,
            current_url="https://app.seedtalent.com/dashboard",
        )
    )

    result = run_auth_preflight(
        mode=AuthMode.VAULT_BACKED_LOGIN,
        storage_state_path=storage_state_path,
        base_url="https://app.seedtalent.com",
        browser_preflight=fake_preflight,
        repo_root=repo_root,
    )

    assert result.status == AuthPreflightStatus.FAILED
    assert result.error_reason == "unsupported_auth_mode"
