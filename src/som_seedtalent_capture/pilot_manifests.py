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


class RunDiagnosticsSnapshot(BaseModel):
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
    notes: list[str] = Field(default_factory=list)


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


def write_model_json(path: str | Path, model: BaseModel | dict[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json") if isinstance(model, BaseModel) else model
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def read_model_json(path: str | Path, model_type: type[BaseModel]) -> BaseModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return model_type.model_validate(payload)
