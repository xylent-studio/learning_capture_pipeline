from pathlib import Path

import pytest

from som_seedtalent_capture import auth as auth_module
from som_seedtalent_capture.auth import (
    AuthMode,
    AuthPreflightStatus,
    BrowserPreflightObservation,
    FakeBrowserAuthPreflight,
    PlaywrightVisibleAuthPreflight,
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


def test_manual_storage_state_path_must_live_under_allowed_root(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    allowed_root = tmp_path / "approved-secrets"
    allowed_root.mkdir()
    storage_state_path = tmp_path / "other-secrets" / "storage_state.json"
    storage_state_path.parent.mkdir(parents=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")

    status = validate_manual_storage_state_path(
        storage_state_path,
        repo_root,
        allowed_root=allowed_root,
    )

    assert status == AuthPreflightStatus.PROHIBITED_PATH


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


def test_run_auth_preflight_rejects_storage_state_outside_allowed_root(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    allowed_root = tmp_path / "approved-secrets"
    allowed_root.mkdir()
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
        mode=AuthMode.MANUAL_STORAGE_STATE,
        storage_state_path=storage_state_path,
        base_url="https://app.seedtalent.com",
        browser_preflight=fake_preflight,
        repo_root=repo_root,
        allowed_storage_root=allowed_root,
    )

    assert result.status == AuthPreflightStatus.PROHIBITED_PATH
    assert result.error_reason == "storage_state_not_allowed"


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


def test_playwright_visible_auth_preflight_waits_for_visible_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    storage_state_path = tmp_path / "outside-secrets" / "storage_state.json"
    storage_state_path.parent.mkdir(parents=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")
    screenshot_dir = tmp_path / "screenshots"
    observed_timeouts: list[int] = []

    class _FakeLocator:
        def __init__(self, page) -> None:
            self._page = page

        def inner_text(self) -> str:
            return self._page.body_text

    class _FakePage:
        def __init__(self) -> None:
            self.url = "https://app.seedtalent.com/"
            self._body_text = ""

        @property
        def body_text(self) -> str:
            return self._body_text

        def goto(self, url: str, wait_until: str | None = None) -> None:
            del wait_until
            self.url = url

        def locator(self, selector: str):
            assert selector == "body"
            return _FakeLocator(self)

        def wait_for_timeout(self, timeout_ms: int) -> None:
            observed_timeouts.append(timeout_ms)
            self._body_text = "Dashboard Course Library Reports Logout"

        def screenshot(self, path: str, full_page: bool = True) -> None:
            del full_page
            Path(path).write_text("fake screenshot", encoding="utf-8")

    class _FakeContext:
        def __init__(self, page: _FakePage) -> None:
            self._page = page

        def new_page(self) -> _FakePage:
            return self._page

    class _FakeBrowser:
        def __init__(self, page: _FakePage) -> None:
            self._page = page

        def new_context(self, storage_state: str):
            assert storage_state.endswith("storage_state.json") or storage_state.endswith("storage-state.json")
            return _FakeContext(self._page)

        def close(self) -> None:
            return None

    class _FakeChromium:
        def __init__(self, page: _FakePage) -> None:
            self._page = page

        def launch(self, headless: bool = True):
            assert headless is True
            return _FakeBrowser(self._page)

    class _FakePlaywrightContext:
        def __init__(self, page: _FakePage) -> None:
            self.chromium = _FakeChromium(page)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_page = _FakePage()
    monkeypatch.setattr(auth_module, "sync_playwright", lambda: _FakePlaywrightContext(fake_page))

    preflight = PlaywrightVisibleAuthPreflight(
        screenshot_dir=screenshot_dir,
        authenticated_indicators=["Dashboard", "Course Library", "Reports"],
        auth_expired_indicators=["Sign in", "Log in", "Login", "Session expired"],
        prohibited_path_patterns=["/settings"],
        headless=True,
    )

    observation = preflight.run(
        storage_state_path=storage_state_path,
        base_url="https://app.seedtalent.com/",
        account_alias="seedtalent-capture-bot",
    )

    assert observation.authenticated is True
    assert "Dashboard" in (observation.visible_state_summary or "")
    assert observation.screenshot_uri is not None
    assert observed_timeouts != []
