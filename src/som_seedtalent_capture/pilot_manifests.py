from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from som_seedtalent_capture.autopilot.capture_plan import CapturePlan
from som_seedtalent_capture.artifacts import ArtifactRecord, RunArtifactLayout
from som_seedtalent_capture.models import new_id


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class PilotBatchStatus(StrEnum):
    CREATED = "created"
    PREFLIGHT_FAILED = "preflight_failed"
    READY_FOR_LIVE_CAPTURE = "ready_for_live_capture"
    NEEDS_RECAPTURE = "needs_recapture"
    COMPLETED = "completed"


class PilotRunStatus(StrEnum):
    QUEUED = "queued"
    PREFLIGHT_FAILED = "preflight_failed"
    BLOCKED_BY_AUTH = "blocked_by_auth"
    READY_FOR_LIVE_CAPTURE = "ready_for_live_capture"
    NEEDS_RECAPTURE = "needs_recapture"
    COMPLETED = "completed"


class FailureStage(StrEnum):
    BATCH_PREFLIGHT = "batch_preflight"
    RUN_PREFLIGHT = "run_preflight"
    RUNNER = "runner"
    PROCESSING = "processing"
    RECONSTRUCTION = "reconstruction"


class FailureCategory(StrEnum):
    AUTH_REQUIRED = "auth_required"
    SHELL_READY_BUT_FRAME_LOADING = "shell_ready_but_frame_loading"
    SCORM_FRAME_NOT_READY = "scorm_frame_not_ready"
    LESSON_GATE_UNHANDLED = "lesson_gate_unhandled"
    QUIZ_RESULTS_EXIT_UNHANDLED = "quiz_results_exit_unhandled"
    SELECTOR_PRIORITY_MISFIRE = "selector_priority_misfire"
    REPEATED_SAME_STATE = "repeated_same_state"
    UNKNOWN_UI_STATE = "unknown_ui_state"
    NO_LIVE_NAVIGATION_AVAILABLE = "no_live_navigation_available"
    PREFLIGHT_BLOCKED = "preflight_blocked"
    EXECUTION_ERROR = "execution_error"


class RunDiagnosticsSnapshot(BaseModel):
    outer_page_url: str | None = None
    outer_page_title: str | None = None
    active_capture_surface_type: str | None = None
    active_capture_surface_name: str | None = None
    active_capture_surface_url: str | None = None
    current_url: str | None = None
    page_title: str | None = None
    visible_state_summary: str | None = None
    screenshot_uri: str | None = None
    prohibited_path_detected: bool = False
    prohibited_path_hits: list[str] = Field(default_factory=list)
    visible_headings: list[str] = Field(default_factory=list)
    visible_buttons: list[str] = Field(default_factory=list)
    visible_links: list[str] = Field(default_factory=list)
    classifier_page_kind: str | None = None
    classifier_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    failure_category: FailureCategory | None = None
    notes: list[str] = Field(default_factory=list)


class PilotExecutionAttempt(BaseModel):
    attempt_number: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=_now_utc)
    lifecycle_status: PilotRunStatus
    stop_reason: str | None = None
    failure_category: FailureCategory | None = None
    diagnostics_snapshot_path: str | None = None
    key_screenshot_uris: list[str] = Field(default_factory=list)


class BatchRunCounts(BaseModel):
    queued_count: int = 0
    ready_for_live_capture_count: int = 0
    blocked_by_auth_count: int = 0
    preflight_failed_count: int = 0
    needs_recapture_count: int = 0
    completed_count: int = 0


class PilotBatchManifest(BaseModel):
    batch_id: str = Field(default_factory=lambda: new_id("pilot_batch"))
    account_alias: str
    runtime_config_path: str
    runtime_config_fingerprint: str
    runner_version: str
    artifact_root: str
    selected_course_count: int = Field(ge=0)
    batch_status: PilotBatchStatus = PilotBatchStatus.CREATED
    counts: BatchRunCounts = Field(default_factory=BatchRunCounts)
    run_manifest_paths: list[str] = Field(default_factory=list)
    batch_preflight_result_path: str | None = None
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)


class PilotRunManifest(BaseModel):
    run_id: str = Field(default_factory=lambda: new_id("pilot_run"))
    batch_id: str
    capture_session_id: str = Field(default_factory=lambda: new_id("session"))
    course_title: str
    source_url: str
    vendor: str | None = None
    permission_basis: str
    rights_status: str
    account_alias: str
    lifecycle_status: PilotRunStatus = PilotRunStatus.QUEUED
    capture_plan: CapturePlan | None = None
    artifact_layout: RunArtifactLayout
    planned_artifacts: list[ArtifactRecord] = Field(default_factory=list)
    runtime_config_path: str
    run_manifest_path: str | None = None
    preflight_result_path: str | None = None
    preflight_status: str | None = None
    preflight_error_reason: str | None = None
    diagnostics_snapshot_path: str | None = None
    diagnostics_snapshot: RunDiagnosticsSnapshot | None = None
    current_blocker_category: FailureCategory | None = None
    recommended_next_action: str | None = None
    qa_report_path: str | None = None
    processing_manifest_path: str | None = None
    reconstruction_summary_path: str | None = None
    failure_bundle_path: str | None = None
    recapture_reasons: list[str] = Field(default_factory=list)
    runner_executed: bool = False
    duration_ms: int | None = Field(default=None, ge=0)
    page_observation_count: int = Field(default=0, ge=0)
    screenshot_uris: list[str] = Field(default_factory=list)
    observed_page_kinds: list[str] = Field(default_factory=list)
    visited_logical_urls: list[str] = Field(default_factory=list)
    completion_detected: bool = False
    unknown_ui_state_detected: bool = False
    runner_stop_reason: str | None = None
    attempts: list[PilotExecutionAttempt] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)


class FailureBundle(BaseModel):
    failure_bundle_id: str = Field(default_factory=lambda: new_id("failure"))
    run_id: str
    batch_id: str
    course_title: str
    source_url: str
    current_status: PilotRunStatus
    failure_stage: FailureStage
    failure_category: FailureCategory | None = None
    error_type: str | None = None
    error_message: str | None = None
    auth_preflight_result: dict[str, object] | None = None
    prohibited_path_hits: list[str] = Field(default_factory=list)
    diagnostics_snapshot: RunDiagnosticsSnapshot | None = None
    suggested_next_action: str
    created_at: datetime = Field(default_factory=_now_utc)


class PilotRunSummary(BaseModel):
    batch_manifest_path: str
    run_manifest_path: str
    status: PilotRunStatus
    qa_readiness_status: str
    failure_bundle_path: str | None = None


class PilotBatchSummary(BaseModel):
    batch_manifest_path: str
    status: PilotBatchStatus
    counts: BatchRunCounts
    run_manifest_paths: list[str] = Field(default_factory=list)


class PilotRunDigest(BaseModel):
    run_manifest_path: str
    lifecycle_status: PilotRunStatus
    attempt_count: int = Field(ge=0)
    stop_reason: str | None = None
    last_observed_page_kind: str | None = None
    active_capture_surface: str | None = None
    current_blocker_category: FailureCategory | None = None
    recommended_next_action: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)


class LiveFindingsDigest(BaseModel):
    owner: str = "runtime"
    source_of_truth: str = "generated_from_run_manifest_and_latest_live_execution"
    refresh_trigger: str = "pilot execute-course or pilot summarize-run"
    maintenance_mode: str = "generated"
    last_validated_at: datetime = Field(default_factory=_now_utc)
    course_title: str
    run_manifest_path: str
    current_blocker_category: FailureCategory | None = None
    stop_reason: str | None = None
    active_capture_surface: str | None = None
    last_observed_page_kind: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    validated_findings: list[str] = Field(default_factory=list)


def write_model_json(path: str | Path, model: BaseModel | dict[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json") if isinstance(model, BaseModel) else model
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def read_model_json(path: str | Path, model_type: type[BaseModel]) -> BaseModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return model_type.model_validate(payload)
