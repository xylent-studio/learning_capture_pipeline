from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class AuthMode(StrEnum):
    MANUAL_STORAGE_STATE = "manual_storage_state"
    VAULT_BACKED_LOGIN = "vault_backed_login"
    MANUAL_REAUTH_ON_EXPIRY = "manual_reauth_on_expiry"


class AuthPreflightStatus(StrEnum):
    AUTHENTICATED = "authenticated"
    AUTH_EXPIRED = "auth_expired"
    PROHIBITED_PATH = "prohibited_path"
    FAILED = "failed"


class BrowserPreflightObservation(BaseModel):
    authenticated: bool
    current_url: str
    visible_state_summary: str | None = None
    screenshot_uri: str | None = None
    prohibited_path_detected: bool = False


class AuthPreflightResult(BaseModel):
    mode: AuthMode
    status: AuthPreflightStatus
    account_alias: str | None = None
    checked_base_url: str
    storage_state_path: str
    screenshot_uri: str | None = None
    visible_state_summary: str | None = None
    current_url: str | None = None
    prohibited_path_detected: bool = False
    error_reason: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.status == AuthPreflightStatus.AUTHENTICATED


class BrowserAuthPreflight(Protocol):
    def run(
        self,
        *,
        storage_state_path: Path,
        base_url: str,
        account_alias: str | None = None,
    ) -> BrowserPreflightObservation:
        ...


class FakeBrowserAuthPreflight:
    def __init__(self, observation: BrowserPreflightObservation) -> None:
        self._observation = observation

    def run(
        self,
        *,
        storage_state_path: Path,
        base_url: str,
        account_alias: str | None = None,
    ) -> BrowserPreflightObservation:
        return self._observation


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_manual_storage_state_path(storage_state_path: Path, repo_root: Path) -> AuthPreflightStatus | None:
    resolved_path = storage_state_path.resolve()
    resolved_repo_root = repo_root.resolve()

    if not resolved_path.exists():
        return AuthPreflightStatus.FAILED

    if not resolved_path.is_file():
        return AuthPreflightStatus.FAILED

    if _is_relative_to(resolved_path, resolved_repo_root):
        return AuthPreflightStatus.PROHIBITED_PATH

    return None


def run_auth_preflight(
    *,
    mode: AuthMode,
    storage_state_path: str | Path,
    base_url: str,
    browser_preflight: BrowserAuthPreflight,
    repo_root: str | Path,
    account_alias: str | None = None,
) -> AuthPreflightResult:
    resolved_storage_state_path = Path(storage_state_path).resolve()
    resolved_repo_root = Path(repo_root).resolve()

    if mode != AuthMode.MANUAL_STORAGE_STATE:
        return AuthPreflightResult(
            mode=mode,
            status=AuthPreflightStatus.FAILED,
            account_alias=account_alias,
            checked_base_url=base_url,
            storage_state_path=str(resolved_storage_state_path),
            error_reason="unsupported_auth_mode",
        )

    path_status = validate_manual_storage_state_path(resolved_storage_state_path, resolved_repo_root)
    if path_status is not None:
        return AuthPreflightResult(
            mode=mode,
            status=path_status,
            account_alias=account_alias,
            checked_base_url=base_url,
            storage_state_path=str(resolved_storage_state_path),
            prohibited_path_detected=path_status == AuthPreflightStatus.PROHIBITED_PATH,
            error_reason="storage_state_not_allowed" if path_status == AuthPreflightStatus.PROHIBITED_PATH else "storage_state_missing_or_invalid",
        )

    observation = browser_preflight.run(
        storage_state_path=resolved_storage_state_path,
        base_url=base_url,
        account_alias=account_alias,
    )

    if observation.prohibited_path_detected:
        status = AuthPreflightStatus.PROHIBITED_PATH
        error_reason = "prohibited_path_detected"
    elif observation.authenticated:
        status = AuthPreflightStatus.AUTHENTICATED
        error_reason = None
    else:
        status = AuthPreflightStatus.AUTH_EXPIRED
        error_reason = "auth_expired"

    return AuthPreflightResult(
        mode=mode,
        status=status,
        account_alias=account_alias,
        checked_base_url=base_url,
        storage_state_path=str(resolved_storage_state_path),
        screenshot_uri=observation.screenshot_uri,
        visible_state_summary=observation.visible_state_summary,
        current_url=observation.current_url,
        prohibited_path_detected=observation.prohibited_path_detected,
        error_reason=error_reason,
    )
