from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from som_seedtalent_capture.auth import AuthMode

DEFAULT_RUNTIME_ROOT = Path(r"C:\dev\_secrets\learning-capture-pipeline")
DEFAULT_ARTIFACT_ROOT = Path(r"C:\dev\_capture_artifacts\learning_capture_pipeline")
DEFAULT_PROHIBITED_PATH_PATTERNS = ["/settings", "/billing", "/account", "/messages", "/support"]
DEFAULT_LOCATOR_PREFERENCES = ["role", "label", "visible_text", "semantic_heading"]
DEFAULT_AUTHENTICATED_INDICATORS = ["Assigned Learning", "Catalog", "Course Overview", "Lesson List"]
DEFAULT_AUTH_EXPIRED_INDICATORS = ["Sign in", "Log in", "Login", "Session expired"]


def _simple_yaml_load(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Install PyYAML to load runtime config") from exc

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("runtime config must be a mapping")
    return payload


def _coerce_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


class ExternalPathConfig(BaseModel):
    secret_root: Path
    permission_manifest_path: Path
    storage_state_path: Path
    auth_screenshot_dir: Path
    artifact_root: Path
    approved_courses_path: Path

    @field_validator(
        "secret_root",
        "permission_manifest_path",
        "storage_state_path",
        "auth_screenshot_dir",
        "artifact_root",
        "approved_courses_path",
        mode="before",
    )
    @classmethod
    def normalize_paths(cls, value: str | Path) -> Path:
        return _coerce_path(value)

    @classmethod
    def windows_local_defaults(cls) -> "ExternalPathConfig":
        secret_root = DEFAULT_RUNTIME_ROOT
        return cls(
            secret_root=secret_root,
            permission_manifest_path=secret_root / "manifests" / "permission_manifest.yaml",
            storage_state_path=secret_root / "playwright" / "storage-state.json",
            auth_screenshot_dir=DEFAULT_ARTIFACT_ROOT / "preflight",
            artifact_root=DEFAULT_ARTIFACT_ROOT,
            approved_courses_path=secret_root / "inputs" / "approved_courses.yaml",
        )


class SelectorTuningConfig(BaseModel):
    visible_locator_preferences: list[str] = Field(default_factory=lambda: list(DEFAULT_LOCATOR_PREFERENCES))
    prohibited_path_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_PROHIBITED_PATH_PATTERNS))
    authenticated_indicators: list[str] = Field(default_factory=lambda: list(DEFAULT_AUTHENTICATED_INDICATORS))
    auth_expired_indicators: list[str] = Field(default_factory=lambda: list(DEFAULT_AUTH_EXPIRED_INDICATORS))
    screenshot_interval_seconds: int = Field(default=5, ge=1)
    navigation_timeout_ms: int = Field(default=15000, ge=1000)
    unchanged_screen_timeout_ms: int = Field(default=10000, ge=1000)
    max_click_retries: int = Field(default=2, ge=0)


class RuntimePilotConfig(BaseModel):
    seedtalent_base_url: str = "https://app.seedtalent.com"
    account_alias: str = "seedtalent-capture-bot"
    auth_mode: AuthMode = AuthMode.MANUAL_STORAGE_STATE
    external_paths: ExternalPathConfig = Field(default_factory=ExternalPathConfig.windows_local_defaults)
    tuning: SelectorTuningConfig = Field(default_factory=SelectorTuningConfig)


class PilotCourseSelectionItem(BaseModel):
    course_title: str
    source_url: str
    vendor: str | None = None
    summary: str | None = None
    capture_priority: int = Field(default=3, ge=0, le=4)
    estimated_duration_minutes: int | None = Field(default=None, ge=1)


class PilotCourseSelection(BaseModel):
    account_alias: str = "seedtalent-capture-bot"
    courses: list[PilotCourseSelectionItem] = Field(default_factory=list)
    notes: str | None = None


def artifact_root() -> Path:
    return _coerce_path(os.environ.get("CAPTURE_ARTIFACT_ROOT", DEFAULT_ARTIFACT_ROOT))


def load_runtime_pilot_config(path: str | Path) -> RuntimePilotConfig:
    payload = _simple_yaml_load(Path(path))
    return RuntimePilotConfig.model_validate(payload)


def load_pilot_course_selection(path: str | Path) -> PilotCourseSelection:
    payload = _simple_yaml_load(Path(path))
    return PilotCourseSelection.model_validate(payload)


def validate_external_runtime_path(path: str | Path, repo_root: str | Path) -> bool:
    resolved_path = _coerce_path(path)
    resolved_repo_root = _coerce_path(repo_root)
    try:
        resolved_path.relative_to(resolved_repo_root)
        return False
    except ValueError:
        return True


def validate_path_within_root(path: str | Path, allowed_root: str | Path) -> bool:
    resolved_path = _coerce_path(path)
    resolved_root = _coerce_path(allowed_root)
    try:
        resolved_path.relative_to(resolved_root)
        return True
    except ValueError:
        return False


def validate_runtime_pilot_paths(config: RuntimePilotConfig, repo_root: str | Path) -> dict[str, bool]:
    return {
        "secret_root_external": validate_external_runtime_path(config.external_paths.secret_root, repo_root),
        "permission_manifest_external": validate_external_runtime_path(config.external_paths.permission_manifest_path, repo_root),
        "permission_manifest_under_secret_root": validate_path_within_root(
            config.external_paths.permission_manifest_path,
            config.external_paths.secret_root,
        ),
        "storage_state_external": validate_external_runtime_path(config.external_paths.storage_state_path, repo_root),
        "storage_state_under_secret_root": validate_path_within_root(
            config.external_paths.storage_state_path,
            config.external_paths.secret_root,
        ),
        "artifact_root_external": validate_external_runtime_path(config.external_paths.artifact_root, repo_root),
        "approved_courses_external": validate_external_runtime_path(config.external_paths.approved_courses_path, repo_root),
        "approved_courses_under_secret_root": validate_path_within_root(
            config.external_paths.approved_courses_path,
            config.external_paths.secret_root,
        ),
        "auth_screenshot_dir_external": validate_external_runtime_path(config.external_paths.auth_screenshot_dir, repo_root),
    }
