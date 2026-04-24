from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright
from pydantic import BaseModel, Field

from som_seedtalent_capture import __version__
from som_seedtalent_capture.artifacts import ArtifactKind, ArtifactRecord, LocalArtifactStore, RunArtifactLayout
from som_seedtalent_capture.autopilot.capture_plan import CapturePlan, QaThresholds, QuizCaptureMode, RecorderProfile
from som_seedtalent_capture.autopilot.course_discovery import CourseDiscoveryResult, CourseInventoryItem
from som_seedtalent_capture.autopilot.recorder import FFmpegRecorderProvider, FakeRecorderProvider, ObsRecorderProvider, RecorderProvider
from som_seedtalent_capture.autopilot.qa import AutopilotQAResult, evaluate_pilot_run_manifest
from som_seedtalent_capture.autopilot.runner import AutopilotRunResult, run_visible_session_autopilot
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
from som_seedtalent_capture.auth import AuthPreflightResult, AuthPreflightStatus, PlaywrightVisibleAuthPreflight, run_auth_preflight
from som_seedtalent_capture.config import PilotCourseSelection, RuntimePilotConfig
from som_seedtalent_capture.models import new_id
from som_seedtalent_capture.permissions import PermissionManifest, authorize_capture
from som_seedtalent_capture.pilot_manifests import (
    BatchRunCounts,
    FailureCategory,
    FailureBundle,
    FailureStage,
    LiveFindingsDigest,
    PilotBatchManifest,
    PilotBatchStatus,
    PilotBatchSummary,
    PilotExecutionAttempt,
    PilotRunDigest,
    PilotRunManifest,
    PilotRunStatus,
    PilotRunSummary,
    RunDiagnosticsSnapshot,
    read_model_json,
    write_model_json,
)
from som_seedtalent_capture.pilot_persistence import persist_pilot_records
from som_seedtalent_capture.processing import ProcessingManifest, build_processing_manifest
from som_seedtalent_capture.scheduler import (
    SchedulerBatchSummary,
    SchedulerConfig,
    block_queue_for_auth,
    build_scheduler_queue,
    mark_queue_ready_for_live_capture,
    summarize_scheduler_results,
)


class AuthBootstrapPreparation(BaseModel):
    account_alias: str
    secret_root: str
    permission_manifest_path: str
    storage_state_path: str
    auth_screenshot_dir: str
    artifact_root: str
    approved_courses_path: str
    created_directories: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)


class PilotBatchMetadata(BaseModel):
    batch_id: str
    account_alias: str
    runner_version: str
    artifact_root: str
    selected_course_count: int = Field(ge=0)
    readiness_status: str
    recapture_status: str


class PilotPlanBundle(BaseModel):
    metadata: PilotBatchMetadata
    plans: list[CapturePlan] = Field(default_factory=list)


def _runtime_config_fingerprint(config_path: str | Path) -> str:
    target = Path(config_path)
    payload = target.read_bytes() if target.exists() else str(target.resolve()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _build_browser_preflight(*, screenshot_dir: str | Path, config: RuntimePilotConfig, headless: bool) -> PlaywrightVisibleAuthPreflight:
    return PlaywrightVisibleAuthPreflight(
        screenshot_dir=screenshot_dir,
        authenticated_indicators=config.tuning.authenticated_indicators,
        auth_expired_indicators=config.tuning.auth_expired_indicators,
        prohibited_path_patterns=config.tuning.prohibited_path_patterns,
        headless=headless,
    )


def _diagnostics_snapshot_from_preflight(result: AuthPreflightResult, config: RuntimePilotConfig) -> RunDiagnosticsSnapshot:
    hits = [pattern for pattern in config.tuning.prohibited_path_patterns if result.current_url and pattern in result.current_url]
    notes = []
    if result.error_reason:
        notes.append(result.error_reason)
    return RunDiagnosticsSnapshot(
        outer_page_url=result.current_url,
        outer_page_title=None,
        active_capture_surface_type="page",
        active_capture_surface_name=None,
        active_capture_surface_url=result.current_url,
        current_url=result.current_url,
        visible_state_summary=result.visible_state_summary,
        screenshot_uri=result.screenshot_uri,
        prohibited_path_detected=result.prohibited_path_detected,
        prohibited_path_hits=hits,
        failure_category=FailureCategory.AUTH_REQUIRED if result.status == AuthPreflightStatus.AUTH_EXPIRED else None,
        notes=notes,
    )


def _diagnostics_snapshot_from_run_result(result: AutopilotRunResult, config: RuntimePilotConfig) -> RunDiagnosticsSnapshot:
    latest_snapshot = result.page_snapshots[-1] if result.page_snapshots else None
    latest_observation = result.observations[-1] if result.observations else None
    current_url = latest_snapshot.execution_url if latest_snapshot else (result.visited_execution_urls[-1] if result.visited_execution_urls else None)
    hits = [pattern for pattern in config.tuning.prohibited_path_patterns if current_url and pattern in current_url]
    notes = [note for note in [result.stopped_reason] if note]
    return RunDiagnosticsSnapshot(
        outer_page_url=latest_snapshot.outer_page_url if latest_snapshot else current_url,
        outer_page_title=latest_snapshot.outer_page_title if latest_snapshot else None,
        active_capture_surface_type=latest_snapshot.active_capture_surface_type if latest_snapshot else None,
        active_capture_surface_name=latest_snapshot.active_capture_surface_name if latest_snapshot else None,
        active_capture_surface_url=latest_snapshot.active_capture_surface_url if latest_snapshot else current_url,
        current_url=current_url,
        page_title=latest_snapshot.title if latest_snapshot else None,
        visible_state_summary=(latest_snapshot.visible_text[:500] if latest_snapshot else None),
        screenshot_uri=latest_snapshot.screenshot_uri if latest_snapshot else None,
        prohibited_path_detected=bool(hits),
        prohibited_path_hits=hits,
        visible_headings=latest_snapshot.headings[:10] if latest_snapshot else [],
        visible_buttons=latest_snapshot.buttons[:12] if latest_snapshot else [],
        visible_links=latest_snapshot.links[:12] if latest_snapshot else [],
        classifier_page_kind=latest_observation.page_kind.value if latest_observation else None,
        classifier_confidence=latest_observation.confidence if latest_observation else None,
        failure_category=result.failure_category,
        notes=notes,
    )


def _outputs_root(config: RuntimePilotConfig) -> Path:
    return config.external_paths.secret_root / "outputs"


def _live_findings_digest_path(config: RuntimePilotConfig) -> Path:
    return _outputs_root(config) / "live-findings-digest.json"


def _summarize_capture_surface(snapshot: RunDiagnosticsSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    if snapshot.active_capture_surface_type == "frame" and snapshot.active_capture_surface_name:
        return f"frame:{snapshot.active_capture_surface_name}"
    if snapshot.current_url and "scormcontent" in snapshot.current_url:
        return f"frame:{snapshot.current_url}"
    if snapshot.active_capture_surface_type is None and snapshot.current_url and "scormcontent" in snapshot.current_url:
        return f"frame:{snapshot.current_url}"
    if snapshot.active_capture_surface_type is None:
        return None
    surface_identity = snapshot.active_capture_surface_name or snapshot.active_capture_surface_url or snapshot.current_url
    return f"{snapshot.active_capture_surface_type}:{surface_identity}" if surface_identity else snapshot.active_capture_surface_type


def _derive_blocker_category(run_manifest: PilotRunManifest) -> FailureCategory | None:
    if run_manifest.current_blocker_category is not None:
        return run_manifest.current_blocker_category

    snapshot = run_manifest.diagnostics_snapshot
    if snapshot is None:
        return None

    headings = {heading.lower() for heading in snapshot.visible_headings}
    buttons = {button.lower() for button in snapshot.visible_buttons}
    if "quiz results" in headings or ("next" in buttons and "take again" in buttons):
        return FailureCategory.QUIZ_RESULTS_EXIT_UNHANDLED
    if snapshot.classifier_page_kind == PageKind.LESSON_INTERACTION_GATE.value:
        return FailureCategory.LESSON_GATE_UNHANDLED
    if snapshot.classifier_page_kind == PageKind.SCORM_FRAME_LOADING.value:
        return FailureCategory.SCORM_FRAME_NOT_READY
    if snapshot.classifier_page_kind == PageKind.COURSE_SHELL_LOADING.value:
        return FailureCategory.SHELL_READY_BUT_FRAME_LOADING
    return None


def _suggest_next_action(
    *,
    preflight_result: AuthPreflightResult | None = None,
    diagnostics_snapshot: RunDiagnosticsSnapshot | None = None,
    failure_category: FailureCategory | None = None,
    stop_reason: str | None = None,
) -> str:
    if preflight_result is not None and preflight_result.status == AuthPreflightStatus.AUTH_EXPIRED:
        return "Refresh the headed browser session and save a new external storage-state file."
    if preflight_result is not None and preflight_result.status == AuthPreflightStatus.PROHIBITED_PATH:
        return "Return to the approved SeedTalent training scope before retrying the pilot."
    if failure_category == FailureCategory.SHELL_READY_BUT_FRAME_LOADING:
        return "Inspect the SCORM launch timing and keep the runner focused on the visible content frame before retrying."
    if failure_category == FailureCategory.SCORM_FRAME_NOT_READY:
        return "Tune frame-ready waits against the SCORM content surface before rerunning this course."
    if failure_category == FailureCategory.LESSON_GATE_UNHANDLED:
        return "Inspect the latest gate screenshot and extend visible interaction handling for that lesson gate."
    if failure_category == FailureCategory.QUIZ_RESULTS_EXIT_UNHANDLED:
        return "Inspect the quiz-results screenshot and prefer visible NEXT or CONTINUE controls over TAKE AGAIN or SKIP."
    if failure_category == FailureCategory.SELECTOR_PRIORITY_MISFIRE:
        return "Adjust live selector priority so visible progression controls outrank SKIP-style controls."
    if failure_category == FailureCategory.REPEATED_SAME_STATE:
        return "Inspect the latest repeated-state screenshots and add a state-specific progression rule for that visible UI."
    if diagnostics_snapshot is not None and diagnostics_snapshot.prohibited_path_detected:
        return "Return to the approved SeedTalent training scope before retrying the pilot."
    if stop_reason:
        return f"Inspect the latest diagnostics bundle for stop_reason={stop_reason} before retrying."
    return "Validate the external storage-state path and rerun auth preflight."


def _artifact_record_by_kind(records: list[ArtifactRecord], kind: ArtifactKind) -> ArtifactRecord | None:
    return next((record for record in records if record.kind == kind), None)


def _replace_artifact_record(records: list[ArtifactRecord], updated_record: ArtifactRecord) -> list[ArtifactRecord]:
    return [updated_record if record.kind == updated_record.kind else record for record in records]


def _build_planned_artifacts(store: LocalArtifactStore, layout: RunArtifactLayout) -> list[ArtifactRecord]:
    return [
        store.build_record(layout=layout, kind=ArtifactKind.SCREEN_RECORDING, name="screen-recording", extension="mp4"),
        store.build_record(layout=layout, kind=ArtifactKind.AUDIO_RECORDING, name="audio-recording", extension="wav"),
        store.build_directory_record(layout=layout, kind=ArtifactKind.SCREENSHOT_FOLDER),
        store.build_record(layout=layout, kind=ArtifactKind.PREFLIGHT_CAPTURE, name="auth-preflight", extension="png"),
        store.build_record(layout=layout, kind=ArtifactKind.QA_REPORT, name="qa-report", extension="json"),
        store.build_record(layout=layout, kind=ArtifactKind.OCR_OUTPUT, name="ocr-output", extension="json"),
        store.build_record(layout=layout, kind=ArtifactKind.TRANSCRIPT_OUTPUT, name="transcript-output", extension="json"),
        store.build_record(layout=layout, kind=ArtifactKind.DIAGNOSTIC_SNAPSHOT, name="diagnostics-snapshot", extension="json"),
    ]


def _processing_manifest_path(layout: RunArtifactLayout) -> Path:
    return Path(layout.processing_dir) / "processing-manifest.json"


def _reconstruction_summary_path(layout: RunArtifactLayout) -> Path:
    return Path(layout.processing_dir) / "reconstruction-summary.json"


def _run_manifest_path(layout: RunArtifactLayout) -> Path:
    return Path(layout.run_root) / "run-manifest.json"


def _batch_manifest_path(batch_root: str | Path) -> Path:
    return Path(batch_root) / "batch-manifest.json"


def _failure_bundle_path(layout: RunArtifactLayout) -> Path:
    return Path(layout.diagnostics_dir) / "failure-bundle.json"


def _preflight_result_path(layout: RunArtifactLayout) -> Path:
    return Path(layout.preflight_dir) / "auth-preflight.json"


def build_run_digest(run_manifest: PilotRunManifest) -> PilotRunDigest:
    blocker_category = _derive_blocker_category(run_manifest)
    evidence_paths = [
        path
        for path in [
            run_manifest.run_manifest_path,
            run_manifest.diagnostics_snapshot_path,
            run_manifest.failure_bundle_path,
            run_manifest.qa_report_path,
            *run_manifest.screenshot_uris[-3:],
        ]
        if path
    ]
    return PilotRunDigest(
        run_manifest_path=str(Path(run_manifest.run_manifest_path or _run_manifest_path(run_manifest.artifact_layout)).resolve()),
        lifecycle_status=run_manifest.lifecycle_status,
        attempt_count=len(run_manifest.attempts),
        stop_reason=run_manifest.runner_stop_reason,
        last_observed_page_kind=(run_manifest.observed_page_kinds[-1] if run_manifest.observed_page_kinds else None),
        active_capture_surface=_summarize_capture_surface(run_manifest.diagnostics_snapshot),
        current_blocker_category=blocker_category,
        recommended_next_action=run_manifest.recommended_next_action
        or _suggest_next_action(
            diagnostics_snapshot=run_manifest.diagnostics_snapshot,
            failure_category=blocker_category,
            stop_reason=run_manifest.runner_stop_reason,
        ),
        evidence_paths=evidence_paths,
    )


def _validated_findings_for_manifest(run_manifest: PilotRunManifest) -> list[str]:
    blocker_category = _derive_blocker_category(run_manifest)
    findings = [
        "Auth sampled too early can look expired until the visible dashboard or course shell stabilizes.",
        "Outer shell readiness is different from visible SCORM content readiness.",
        "Course content is usually inside the visible SCORM frame, not the outer SeedTalent shell.",
        "Lesson interaction gates can block progression and may require clicking the visible label wrapper for checkboxes.",
        "Quiz flow contains intro, question, results, and exit states.",
        "Hidden or low-value skip controls should not outrank visible progression controls.",
    ]
    if blocker_category == FailureCategory.QUIZ_RESULTS_EXIT_UNHANDLED:
        findings.append("Current highest-value live blocker is the quiz-results exit transition after the visible score/results state.")
    return findings


def write_live_findings_digest(*, config: RuntimePilotConfig, run_manifest: PilotRunManifest) -> Path:
    blocker_category = _derive_blocker_category(run_manifest)
    digest = LiveFindingsDigest(
        course_title=run_manifest.course_title,
        run_manifest_path=str(Path(run_manifest.run_manifest_path or _run_manifest_path(run_manifest.artifact_layout)).resolve()),
        current_blocker_category=blocker_category,
        stop_reason=run_manifest.runner_stop_reason,
        active_capture_surface=_summarize_capture_surface(run_manifest.diagnostics_snapshot),
        last_observed_page_kind=(run_manifest.observed_page_kinds[-1] if run_manifest.observed_page_kinds else None),
        evidence_paths=build_run_digest(run_manifest).evidence_paths,
        validated_findings=_validated_findings_for_manifest(run_manifest),
    )
    target = _live_findings_digest_path(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_model_json(target, digest)
    return target


def _build_run_manifest(
    *,
    batch_id: str,
    account_alias: str,
    runtime_config_path: str | Path,
    plan: CapturePlan,
    layout: RunArtifactLayout,
    planned_artifacts: list[ArtifactRecord],
    run_id: str | None = None,
) -> PilotRunManifest:
    qa_report = _artifact_record_by_kind(planned_artifacts, ArtifactKind.QA_REPORT)
    diagnostics = _artifact_record_by_kind(planned_artifacts, ArtifactKind.DIAGNOSTIC_SNAPSHOT)
    return PilotRunManifest(
        run_id=run_id or new_id("pilot_run"),
        batch_id=batch_id,
        course_title=plan.course_title,
        source_url=plan.source_url,
        permission_basis=plan.permission_basis,
        rights_status=plan.rights_status.value,
        account_alias=account_alias,
        capture_plan=plan,
        artifact_layout=layout,
        planned_artifacts=planned_artifacts,
        runtime_config_path=str(Path(runtime_config_path).resolve()),
        qa_report_path=qa_report.local_path if qa_report else None,
        diagnostics_snapshot_path=diagnostics.local_path if diagnostics else None,
        processing_manifest_path=str(_processing_manifest_path(layout).resolve()),
        reconstruction_summary_path=str(_reconstruction_summary_path(layout).resolve()),
    )


def _reconcile_runtime_artifacts(
    *,
    run_manifest: PilotRunManifest,
    preflight_result: AuthPreflightResult,
    diagnostics_path: str | Path,
) -> PilotRunManifest:
    planned_artifacts = list(run_manifest.planned_artifacts)
    preflight_record = _artifact_record_by_kind(planned_artifacts, ArtifactKind.PREFLIGHT_CAPTURE)
    if preflight_record is not None and preflight_result.screenshot_uri is not None:
        preflight_record = preflight_record.model_copy(update={"local_path": preflight_result.screenshot_uri}, deep=True)
        planned_artifacts = _replace_artifact_record(planned_artifacts, preflight_record)
    diagnostics_record = _artifact_record_by_kind(planned_artifacts, ArtifactKind.DIAGNOSTIC_SNAPSHOT)
    if diagnostics_record is not None:
        diagnostics_record = diagnostics_record.model_copy(update={"local_path": str(Path(diagnostics_path).resolve())}, deep=True)
        planned_artifacts = _replace_artifact_record(planned_artifacts, diagnostics_record)
    return run_manifest.model_copy(update={"planned_artifacts": planned_artifacts}, deep=True)


def _update_batch_counts(batch_manifest: PilotBatchManifest, run_manifests: list[PilotRunManifest]) -> PilotBatchManifest:
    counts = BatchRunCounts(
        queued_count=sum(1 for run in run_manifests if run.lifecycle_status == PilotRunStatus.QUEUED),
        ready_for_live_capture_count=sum(1 for run in run_manifests if run.lifecycle_status == PilotRunStatus.READY_FOR_LIVE_CAPTURE),
        blocked_by_auth_count=sum(1 for run in run_manifests if run.lifecycle_status == PilotRunStatus.BLOCKED_BY_AUTH),
        preflight_failed_count=sum(1 for run in run_manifests if run.lifecycle_status == PilotRunStatus.PREFLIGHT_FAILED),
        needs_recapture_count=sum(1 for run in run_manifests if run.lifecycle_status == PilotRunStatus.NEEDS_RECAPTURE),
        completed_count=sum(1 for run in run_manifests if run.lifecycle_status == PilotRunStatus.COMPLETED),
    )
    return batch_manifest.model_copy(
        update={
            "counts": counts,
            "run_manifest_paths": [str(_run_manifest_path(run.artifact_layout).resolve()) for run in run_manifests],
        },
        deep=True,
    )


def _write_processing_manifest(run_manifest: PilotRunManifest) -> ProcessingManifest:
    processing_manifest = build_processing_manifest(run_manifest)
    write_model_json(run_manifest.processing_manifest_path, processing_manifest)
    return processing_manifest


def _write_qa_report(run_manifest: PilotRunManifest) -> AutopilotQAResult:
    qa_result = evaluate_pilot_run_manifest(run_manifest=run_manifest)
    if run_manifest.qa_report_path:
        write_model_json(run_manifest.qa_report_path, qa_result.qa_report)
    return qa_result


def _write_failure_bundle(
    *,
    run_manifest: PilotRunManifest,
    stage: FailureStage,
    auth_preflight_result: AuthPreflightResult | None,
    diagnostics_snapshot: RunDiagnosticsSnapshot | None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> FailureBundle:
    bundle = FailureBundle(
        run_id=run_manifest.run_id,
        batch_id=run_manifest.batch_id,
        course_title=run_manifest.course_title,
        source_url=run_manifest.source_url,
        current_status=run_manifest.lifecycle_status,
        failure_stage=stage,
        failure_category=run_manifest.current_blocker_category or (diagnostics_snapshot.failure_category if diagnostics_snapshot else None),
        error_type=error_type,
        error_message=error_message,
        auth_preflight_result=auth_preflight_result.model_dump(mode="json") if auth_preflight_result is not None else None,
        prohibited_path_hits=diagnostics_snapshot.prohibited_path_hits if diagnostics_snapshot else [],
        diagnostics_snapshot=diagnostics_snapshot,
        suggested_next_action=_suggest_next_action(
            preflight_result=auth_preflight_result,
            diagnostics_snapshot=diagnostics_snapshot,
            failure_category=run_manifest.current_blocker_category or (diagnostics_snapshot.failure_category if diagnostics_snapshot else None),
            stop_reason=run_manifest.runner_stop_reason,
        ),
    )
    path = _failure_bundle_path(run_manifest.artifact_layout)
    write_model_json(path, bundle)
    return bundle


def _recorder_provider_for_profile(profile: RecorderProfile) -> RecorderProvider | None:
    if profile == RecorderProfile.FIXTURE_NOOP:
        return FakeRecorderProvider()
    if profile == RecorderProfile.HEADED_BROWSER_OBS:
        return ObsRecorderProvider()
    if profile == RecorderProfile.HEADED_BROWSER_FFMPEG:
        return FFmpegRecorderProvider()
    return None


def _update_run_manifest_from_execution(
    *,
    run_manifest: PilotRunManifest,
    run_result: AutopilotRunResult,
    diagnostics_snapshot: RunDiagnosticsSnapshot,
) -> PilotRunManifest:
    planned_artifacts = list(run_manifest.planned_artifacts)
    screen_recording = _artifact_record_by_kind(planned_artifacts, ArtifactKind.SCREEN_RECORDING)
    audio_recording = _artifact_record_by_kind(planned_artifacts, ArtifactKind.AUDIO_RECORDING)

    if run_result.recorder_session is not None and screen_recording is not None:
        screen_recording = screen_recording.model_copy(
            update={"local_path": run_result.recorder_session.video_uri},
            deep=True,
        )
        planned_artifacts = _replace_artifact_record(planned_artifacts, screen_recording)
    if run_result.recorder_session is not None and audio_recording is not None and run_result.recorder_session.audio_uri is not None:
        audio_recording = audio_recording.model_copy(
            update={"local_path": run_result.recorder_session.audio_uri},
            deep=True,
        )
        planned_artifacts = _replace_artifact_record(planned_artifacts, audio_recording)

    unique_screenshots = list(dict.fromkeys(snapshot.screenshot_uri for snapshot in run_result.page_snapshots))
    duration_ms = max((event.timestamp_ms for event in run_result.events), default=0)
    attempt = PilotExecutionAttempt(
        attempt_number=len(run_manifest.attempts) + 1,
        lifecycle_status=PilotRunStatus.COMPLETED if run_result.completion_detected else PilotRunStatus.NEEDS_RECAPTURE,
        stop_reason=run_result.stopped_reason,
        failure_category=run_result.failure_category,
        diagnostics_snapshot_path=run_manifest.diagnostics_snapshot_path,
        key_screenshot_uris=unique_screenshots[-3:],
    )
    recommended_next_action = _suggest_next_action(
        diagnostics_snapshot=diagnostics_snapshot,
        failure_category=run_result.failure_category,
        stop_reason=run_result.stopped_reason,
    )

    return run_manifest.model_copy(
        update={
            "planned_artifacts": planned_artifacts,
            "runner_executed": True,
            "duration_ms": duration_ms,
            "page_observation_count": len(run_result.observations),
            "screenshot_uris": unique_screenshots,
            "observed_page_kinds": [observation.page_kind.value for observation in run_result.observations],
            "visited_logical_urls": run_result.visited_logical_urls,
            "completion_detected": run_result.completion_detected,
            "unknown_ui_state_detected": run_result.unknown_ui_state_detected,
            "runner_stop_reason": run_result.stopped_reason,
            "diagnostics_snapshot": diagnostics_snapshot,
            "current_blocker_category": run_result.failure_category,
            "recommended_next_action": recommended_next_action,
            "attempts": [*run_manifest.attempts, attempt],
        },
        deep=True,
    )


def _load_batch_manifest(path: str | Path) -> PilotBatchManifest:
    return read_model_json(path, PilotBatchManifest)  # type: ignore[return-value]


def _collect_batch_run_manifests(batch_manifest: PilotBatchManifest, updated_run_manifest: PilotRunManifest) -> list[PilotRunManifest]:
    manifests: list[PilotRunManifest] = []
    updated_run_manifest_path = str(Path(updated_run_manifest.run_manifest_path or _run_manifest_path(updated_run_manifest.artifact_layout)).resolve())
    seen_updated = False

    for path in batch_manifest.run_manifest_paths:
        resolved = str(Path(path).resolve())
        if resolved == updated_run_manifest_path:
            manifests.append(updated_run_manifest)
            seen_updated = True
            continue
        target = Path(resolved)
        if target.exists():
            manifests.append(read_model_json(target, PilotRunManifest))  # type: ignore[arg-type]

    if not seen_updated:
        manifests.append(updated_run_manifest)
    return manifests


def _run_auth_preflight_for_path(
    *,
    config: RuntimePilotConfig,
    screenshot_dir: str | Path,
    repo_root: str | Path,
    account_alias: str,
    headless: bool,
) -> AuthPreflightResult:
    browser_preflight = _build_browser_preflight(
        screenshot_dir=screenshot_dir,
        config=config,
        headless=headless,
    )
    return run_auth_preflight(
        mode=config.auth_mode,
        storage_state_path=config.external_paths.storage_state_path,
        base_url=config.seedtalent_base_url,
        browser_preflight=browser_preflight,
        repo_root=repo_root,
        account_alias=account_alias,
        allowed_storage_root=config.external_paths.secret_root,
    )


def prepare_auth_bootstrap(config: RuntimePilotConfig) -> AuthBootstrapPreparation:
    created_directories: list[str] = []
    directories = [
        config.external_paths.secret_root,
        config.external_paths.permission_manifest_path.parent,
        config.external_paths.storage_state_path.parent,
        config.external_paths.auth_screenshot_dir,
        config.external_paths.artifact_root,
        config.external_paths.approved_courses_path.parent,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        created_directories.append(str(directory))
    return AuthBootstrapPreparation(
        account_alias=config.account_alias,
        secret_root=str(config.external_paths.secret_root),
        permission_manifest_path=str(config.external_paths.permission_manifest_path),
        storage_state_path=str(config.external_paths.storage_state_path),
        auth_screenshot_dir=str(config.external_paths.auth_screenshot_dir),
        artifact_root=str(config.external_paths.artifact_root),
        approved_courses_path=str(config.external_paths.approved_courses_path),
        created_directories=created_directories,
        recommended_commands=[
            "som-capture pilot validate-config --config <runtime-config.yaml>",
            "som-capture pilot bootstrap-auth --config <runtime-config.yaml>",
            "som-capture pilot auth-preflight --config <runtime-config.yaml> --headed",
            "som-capture pilot discovery --config <runtime-config.yaml> --headed",
            "som-capture pilot plans-from-approved --config <runtime-config.yaml>",
            "som-capture pilot run-course --config <runtime-config.yaml> --plan-bundle <plans.json>",
        ],
    )


def _extract_visible_course_cards(page: Page) -> list[dict[str, str | None]]:
    cards = []
    card_locator = page.locator("section.course-card, article.course-card, [data-course-card]")
    for index in range(card_locator.count()):
        card = card_locator.nth(index)
        link = card.locator("a").first
        heading = card.locator("h1, h2, h3").first
        vendor_text = next(
            (text for text in card.locator("p").all_inner_texts() if text.lower().startswith("vendor:")),
            None,
        )
        paragraphs = [text.strip() for text in card.locator("p").all_inner_texts() if text.strip()]
        summary = next((text for text in paragraphs if not text.lower().startswith("vendor:") and "assigned course" not in text.lower()), None)
        course_title = heading.inner_text().strip() if heading.count() else None
        href = link.get_attribute("href") if link.count() else None
        cards.append(
            {
                "course_title": course_title,
                "vendor": vendor_text.split(":", maxsplit=1)[1].strip() if vendor_text else None,
                "summary": summary,
                "href": href,
            }
        )
    return cards


def load_pilot_plan_bundle(path: str | Path) -> PilotPlanBundle:
    return read_model_json(path, PilotPlanBundle)  # type: ignore[return-value]


def summarize_pilot_run(
    *,
    config: RuntimePilotConfig,
    run_manifest_path: str | Path,
) -> PilotRunDigest:
    run_manifest = read_model_json(run_manifest_path, PilotRunManifest)  # type: ignore[assignment]
    run_manifest = run_manifest.model_copy(update={"run_manifest_path": str(Path(run_manifest_path).resolve())}, deep=True)
    write_live_findings_digest(config=config, run_manifest=run_manifest)
    return build_run_digest(run_manifest)


def run_visible_catalog_discovery(
    *,
    config: RuntimePilotConfig,
    manifest: PermissionManifest,
    headless: bool = True,
) -> CourseDiscoveryResult:
    config.external_paths.auth_screenshot_dir.mkdir(parents=True, exist_ok=True)
    preflight_result = _run_auth_preflight_for_path(
        config=config,
        screenshot_dir=config.external_paths.auth_screenshot_dir,
        repo_root=Path.cwd(),
        account_alias=config.account_alias,
        headless=headless,
    )
    if preflight_result.status != AuthPreflightStatus.AUTHENTICATED:
        raise ValueError(f"catalog discovery requires authenticated preflight, got {preflight_result.status.value}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(config.external_paths.storage_state_path))
        page = context.new_page()
        page.goto(config.seedtalent_base_url, wait_until="domcontentloaded")
        current_url = page.url
        screenshot_uri = str((config.external_paths.auth_screenshot_dir / "catalog-discovery.png").resolve())
        page.screenshot(path=screenshot_uri, full_page=True)
        cards = _extract_visible_course_cards(page)
        observation = PageObservation(
            url=current_url,
            title=page.title(),
            page_kind=PageKind.CATALOG,
            visible_text_sample=page.locator("body").inner_text()[:300],
            buttons=[text.strip() for text in page.locator("button:visible").all_inner_texts() if text.strip()],
            links=[text.strip() for text in page.locator("a:visible").all_inner_texts() if text.strip()],
            screenshot_uri=screenshot_uri,
            confidence=0.75,
        )
        browser.close()

    items = [
        CourseInventoryItem(
            course_title=card["course_title"] or "Unknown course",
            vendor=card["vendor"],
            source_url=urljoin(current_url, card["href"] or ""),
            catalog_url=current_url,
            screenshot_uri=screenshot_uri,
            summary=card["summary"],
            discovery_page_kind=PageKind.CATALOG,
            authorization=authorize_capture(
                url=urljoin(current_url, card["href"] or ""),
                vendor=card["vendor"],
                course_title=card["course_title"],
                manifest=manifest,
            ),
        )
        for card in cards
    ]

    return CourseDiscoveryResult(
        catalog_url=current_url,
        screenshot_uri=screenshot_uri,
        observation=observation,
        items=items,
    )


def build_pilot_plan_bundle(
    *,
    selection: PilotCourseSelection,
    config: RuntimePilotConfig,
    plans: list[CapturePlan],
) -> PilotPlanBundle:
    return PilotPlanBundle(
        metadata=PilotBatchMetadata(
            batch_id=f"pilot-{config.account_alias}",
            account_alias=selection.account_alias or config.account_alias,
            runner_version=__version__,
            artifact_root=str(config.external_paths.artifact_root),
            selected_course_count=len(selection.courses),
            readiness_status="ready_for_live_auth",
            recapture_status="none",
        ),
        plans=plans,
    )


def build_capture_plans_from_selection(
    *,
    selection: PilotCourseSelection,
    config: RuntimePilotConfig,
    manifest: PermissionManifest,
) -> list[CapturePlan]:
    plans: list[CapturePlan] = []
    for course in selection.courses:
        authorization = authorize_capture(
            url=course.source_url,
            vendor=course.vendor,
            course_title=course.course_title,
            manifest=manifest,
        )
        if not authorization.authorized:
            raise ValueError(f"Approved course input is not authorized: {course.course_title}")

        plans.append(
            CapturePlan(
                course_title=course.course_title,
                source_url=course.source_url,
                permission_basis=authorization.permission_basis,
                rights_status=authorization.rights_status,
                screenshot_interval_seconds=config.tuning.screenshot_interval_seconds,
                recorder_profile=RecorderProfile.HEADED_BROWSER_FFMPEG,
                quiz_mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT,
                max_course_duration_minutes=course.estimated_duration_minutes or 60,
                expected_lesson_count=None,
                lesson_list_url=None,
                lesson_urls=[],
                lesson_list_observation=None,
                qa_thresholds=QaThresholds(
                    min_page_observations=1,
                    min_screenshot_count=1,
                    min_classifier_confidence=0.7,
                    require_quiz_capture=True,
                    require_completion_capture=True,
                ),
            )
        )
    return plans


def _select_plan(bundle: PilotPlanBundle, course_url: str | None) -> CapturePlan:
    if course_url is None:
        if len(bundle.plans) != 1:
            raise ValueError("plan bundle must contain exactly one plan when --course-url is not provided")
        return bundle.plans[0]
    matches = [plan for plan in bundle.plans if plan.source_url == course_url]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one plan for course_url={course_url}")
    return matches[0]


def run_pilot_course_skeleton(
    *,
    config: RuntimePilotConfig,
    config_path: str | Path,
    plan_bundle: PilotPlanBundle,
    course_url: str | None = None,
    headless: bool = True,
    database_url: str | None = None,
) -> PilotRunSummary:
    selected_plan = _select_plan(plan_bundle, course_url)
    batch_id = plan_bundle.metadata.batch_id or new_id("pilot_batch")
    store = LocalArtifactStore(config.external_paths.artifact_root)
    layout = store.ensure_run_layout(
        batch_id=batch_id,
        run_id=new_id("pilot_run"),
        course_title=selected_plan.course_title,
    )
    planned_artifacts = _build_planned_artifacts(store, layout)
    run_manifest = _build_run_manifest(
        batch_id=batch_id,
        account_alias=config.account_alias,
        runtime_config_path=config_path,
        plan=selected_plan,
        layout=layout,
        planned_artifacts=planned_artifacts,
        run_id=Path(layout.run_root).name.split("-", maxsplit=1)[0],
    )
    batch_manifest = PilotBatchManifest(
        batch_id=batch_id,
        account_alias=config.account_alias,
        runtime_config_path=str(Path(config_path).resolve()),
        runtime_config_fingerprint=_runtime_config_fingerprint(config_path),
        runner_version=__version__,
        artifact_root=str(config.external_paths.artifact_root),
        selected_course_count=1,
    )
    batch_manifest = _update_batch_counts(batch_manifest, [run_manifest])
    write_model_json(_batch_manifest_path(layout.batch_root), batch_manifest)
    run_manifest_path = write_model_json(_run_manifest_path(layout), run_manifest)
    run_manifest = run_manifest.model_copy(update={"run_manifest_path": str(run_manifest_path.resolve())}, deep=True)
    write_model_json(_run_manifest_path(layout), run_manifest)
    _write_processing_manifest(run_manifest)

    preflight_result = _run_auth_preflight_for_path(
        config=config,
        screenshot_dir=layout.preflight_dir,
        repo_root=Path.cwd(),
        account_alias=config.account_alias,
        headless=headless,
    )
    preflight_path = write_model_json(_preflight_result_path(layout), preflight_result)
    diagnostics_snapshot = _diagnostics_snapshot_from_preflight(preflight_result, config)
    diagnostics_path = write_model_json(Path(layout.diagnostics_dir) / "diagnostics-snapshot.json", diagnostics_snapshot)

    lifecycle_status = (
        PilotRunStatus.READY_FOR_LIVE_CAPTURE
        if preflight_result.status == AuthPreflightStatus.AUTHENTICATED
        else PilotRunStatus.PREFLIGHT_FAILED
    )
    run_manifest = run_manifest.model_copy(
        update={
            "lifecycle_status": lifecycle_status,
            "preflight_result_path": str(preflight_path.resolve()),
            "preflight_status": preflight_result.status.value,
            "preflight_error_reason": preflight_result.error_reason,
            "diagnostics_snapshot_path": str(diagnostics_path.resolve()),
            "diagnostics_snapshot": diagnostics_snapshot,
            "current_blocker_category": diagnostics_snapshot.failure_category,
            "recommended_next_action": _suggest_next_action(
                preflight_result=preflight_result,
                diagnostics_snapshot=diagnostics_snapshot,
                failure_category=diagnostics_snapshot.failure_category,
            ),
        },
        deep=True,
    )
    run_manifest = _reconcile_runtime_artifacts(
        run_manifest=run_manifest,
        preflight_result=preflight_result,
        diagnostics_path=diagnostics_path,
    )

    failure_bundle_path: str | None = None
    if lifecycle_status == PilotRunStatus.PREFLIGHT_FAILED:
        failure_bundle = _write_failure_bundle(
            run_manifest=run_manifest,
            stage=FailureStage.RUN_PREFLIGHT,
            auth_preflight_result=preflight_result,
            diagnostics_snapshot=diagnostics_snapshot,
        )
        failure_bundle_path = str(_failure_bundle_path(layout).resolve())
        run_manifest = run_manifest.model_copy(update={"failure_bundle_path": failure_bundle_path}, deep=True)

    qa_result = _write_qa_report(run_manifest)
    batch_status = (
        PilotBatchStatus.READY_FOR_LIVE_CAPTURE
        if lifecycle_status == PilotRunStatus.READY_FOR_LIVE_CAPTURE
        else PilotBatchStatus.PREFLIGHT_FAILED
    )
    batch_manifest = _update_batch_counts(
        batch_manifest.model_copy(update={"batch_status": batch_status}, deep=True),
        [run_manifest],
    )

    write_model_json(_run_manifest_path(layout), run_manifest)
    write_model_json(_batch_manifest_path(layout.batch_root), batch_manifest)
    persist_pilot_records(
        database_url=database_url,
        batch_manifest=batch_manifest,
        run_manifests=[run_manifest],
        qa_results={run_manifest.run_id: qa_result},
    )

    return PilotRunSummary(
        batch_manifest_path=str(_batch_manifest_path(layout.batch_root).resolve()),
        run_manifest_path=str(_run_manifest_path(layout).resolve()),
        status=run_manifest.lifecycle_status,
        qa_readiness_status=qa_result.readiness_status.value,
        failure_bundle_path=failure_bundle_path,
    )


def execute_pilot_course(
    *,
    config: RuntimePilotConfig,
    run_manifest_path: str | Path,
    headless: bool = True,
    database_url: str | None = None,
) -> PilotRunSummary:
    run_manifest = read_model_json(run_manifest_path, PilotRunManifest)  # type: ignore[assignment]
    if run_manifest.capture_plan is None:
        raise ValueError("run manifest is missing capture_plan and cannot be executed")

    run_manifest = run_manifest.model_copy(update={"run_manifest_path": str(Path(run_manifest_path).resolve())}, deep=True)
    batch_manifest_path = _batch_manifest_path(run_manifest.artifact_layout.batch_root)
    batch_manifest = _load_batch_manifest(batch_manifest_path)

    preflight_result = _run_auth_preflight_for_path(
        config=config,
        screenshot_dir=run_manifest.artifact_layout.preflight_dir,
        repo_root=Path.cwd(),
        account_alias=config.account_alias,
        headless=headless,
    )
    preflight_path = write_model_json(_preflight_result_path(run_manifest.artifact_layout), preflight_result)
    diagnostics_snapshot = _diagnostics_snapshot_from_preflight(preflight_result, config)
    diagnostics_path = write_model_json(
        Path(run_manifest.artifact_layout.diagnostics_dir) / "diagnostics-snapshot.json",
        diagnostics_snapshot,
    )
    run_manifest = run_manifest.model_copy(
        update={
            "preflight_result_path": str(preflight_path.resolve()),
            "preflight_status": preflight_result.status.value,
            "preflight_error_reason": preflight_result.error_reason,
            "diagnostics_snapshot_path": str(diagnostics_path.resolve()),
            "diagnostics_snapshot": diagnostics_snapshot,
            "current_blocker_category": diagnostics_snapshot.failure_category,
            "recommended_next_action": _suggest_next_action(
                preflight_result=preflight_result,
                diagnostics_snapshot=diagnostics_snapshot,
                failure_category=diagnostics_snapshot.failure_category,
            ),
        },
        deep=True,
    )
    run_manifest = _reconcile_runtime_artifacts(
        run_manifest=run_manifest,
        preflight_result=preflight_result,
        diagnostics_path=diagnostics_path,
    )

    failure_bundle_path: str | None = None
    qa_result: AutopilotQAResult

    if preflight_result.status != AuthPreflightStatus.AUTHENTICATED:
        run_manifest = run_manifest.model_copy(
            update={
                "lifecycle_status": PilotRunStatus.PREFLIGHT_FAILED,
                "attempts": [
                    *run_manifest.attempts,
                    PilotExecutionAttempt(
                        attempt_number=len(run_manifest.attempts) + 1,
                        lifecycle_status=PilotRunStatus.PREFLIGHT_FAILED,
                        stop_reason=preflight_result.status.value,
                        failure_category=diagnostics_snapshot.failure_category,
                        diagnostics_snapshot_path=str(diagnostics_path.resolve()),
                        key_screenshot_uris=[preflight_result.screenshot_uri] if preflight_result.screenshot_uri else [],
                    ),
                ],
            },
            deep=True,
        )
        _write_processing_manifest(run_manifest)
        _write_failure_bundle(
            run_manifest=run_manifest,
            stage=FailureStage.RUN_PREFLIGHT,
            auth_preflight_result=preflight_result,
            diagnostics_snapshot=diagnostics_snapshot,
        )
        failure_bundle_path = str(_failure_bundle_path(run_manifest.artifact_layout).resolve())
        run_manifest = run_manifest.model_copy(update={"failure_bundle_path": failure_bundle_path}, deep=True)
        qa_result = _write_qa_report(run_manifest)
    else:
        try:
            run_result = run_visible_session_autopilot(
                plan=run_manifest.capture_plan,
                artifact_root=run_manifest.artifact_layout.run_root,
                storage_state_path=config.external_paths.storage_state_path,
                headless=headless,
                recorder_provider=_recorder_provider_for_profile(run_manifest.capture_plan.recorder_profile),
            )
            diagnostics_snapshot = _diagnostics_snapshot_from_run_result(run_result, config)
            diagnostics_path = write_model_json(
                Path(run_manifest.artifact_layout.diagnostics_dir) / "diagnostics-snapshot.json",
                diagnostics_snapshot,
            )
            run_manifest = _update_run_manifest_from_execution(
                run_manifest=run_manifest,
                run_result=run_result,
                diagnostics_snapshot=diagnostics_snapshot,
            )
            run_manifest = run_manifest.model_copy(
                update={
                    "lifecycle_status": PilotRunStatus.COMPLETED,
                    "diagnostics_snapshot_path": str(diagnostics_path.resolve()),
                },
                deep=True,
            )
            _write_processing_manifest(run_manifest)
            qa_result = _write_qa_report(run_manifest)
            lifecycle_status = (
                PilotRunStatus.COMPLETED
                if qa_result.readiness_status.value == "ready_for_reconstruction"
                else PilotRunStatus.NEEDS_RECAPTURE
            )
            run_manifest = run_manifest.model_copy(
                update={
                    "lifecycle_status": lifecycle_status,
                    "recapture_reasons": [reason.value for reason in qa_result.recapture_reasons],
                },
                deep=True,
            )
            if run_manifest.unknown_ui_state_detected or diagnostics_snapshot.prohibited_path_detected:
                _write_failure_bundle(
                    run_manifest=run_manifest,
                    stage=FailureStage.RUNNER,
                    auth_preflight_result=preflight_result,
                    diagnostics_snapshot=diagnostics_snapshot,
                )
                failure_bundle_path = str(_failure_bundle_path(run_manifest.artifact_layout).resolve())
                run_manifest = run_manifest.model_copy(update={"failure_bundle_path": failure_bundle_path}, deep=True)
        except Exception as exc:
            run_manifest = run_manifest.model_copy(
                update={
                    "runner_executed": True,
                    "lifecycle_status": PilotRunStatus.NEEDS_RECAPTURE,
                    "runner_stop_reason": exc.__class__.__name__,
                    "current_blocker_category": FailureCategory.EXECUTION_ERROR,
                    "recommended_next_action": _suggest_next_action(
                        diagnostics_snapshot=diagnostics_snapshot,
                        failure_category=FailureCategory.EXECUTION_ERROR,
                        stop_reason=exc.__class__.__name__,
                    ),
                    "attempts": [
                        *run_manifest.attempts,
                        PilotExecutionAttempt(
                            attempt_number=len(run_manifest.attempts) + 1,
                            lifecycle_status=PilotRunStatus.NEEDS_RECAPTURE,
                            stop_reason=exc.__class__.__name__,
                            failure_category=FailureCategory.EXECUTION_ERROR,
                            diagnostics_snapshot_path=str(diagnostics_path.resolve()),
                            key_screenshot_uris=run_manifest.screenshot_uris[-3:],
                        ),
                    ],
                },
                deep=True,
            )
            _write_processing_manifest(run_manifest)
            _write_failure_bundle(
                run_manifest=run_manifest,
                stage=FailureStage.RUNNER,
                auth_preflight_result=preflight_result,
                diagnostics_snapshot=diagnostics_snapshot,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            failure_bundle_path = str(_failure_bundle_path(run_manifest.artifact_layout).resolve())
            run_manifest = run_manifest.model_copy(update={"failure_bundle_path": failure_bundle_path}, deep=True)
            qa_result = _write_qa_report(run_manifest)

    write_model_json(_run_manifest_path(run_manifest.artifact_layout), run_manifest)
    write_live_findings_digest(config=config, run_manifest=run_manifest)
    batch_run_manifests = _collect_batch_run_manifests(batch_manifest, run_manifest)
    batch_status = (
        PilotBatchStatus.COMPLETED
        if all(item.lifecycle_status == PilotRunStatus.COMPLETED for item in batch_run_manifests)
        else PilotBatchStatus.NEEDS_RECAPTURE
        if any(item.lifecycle_status == PilotRunStatus.NEEDS_RECAPTURE for item in batch_run_manifests)
        else PilotBatchStatus.PREFLIGHT_FAILED
        if any(item.lifecycle_status in {PilotRunStatus.PREFLIGHT_FAILED, PilotRunStatus.BLOCKED_BY_AUTH} for item in batch_run_manifests)
        else PilotBatchStatus.READY_FOR_LIVE_CAPTURE
    )
    batch_manifest = _update_batch_counts(
        batch_manifest.model_copy(update={"batch_status": batch_status}, deep=True),
        batch_run_manifests,
    )
    write_model_json(batch_manifest_path, batch_manifest)
    persist_pilot_records(
        database_url=database_url,
        batch_manifest=batch_manifest,
        run_manifests=batch_run_manifests,
        qa_results={run_manifest.run_id: qa_result},
    )

    return PilotRunSummary(
        batch_manifest_path=str(batch_manifest_path.resolve()),
        run_manifest_path=str(_run_manifest_path(run_manifest.artifact_layout).resolve()),
        status=run_manifest.lifecycle_status,
        qa_readiness_status=qa_result.readiness_status.value,
        failure_bundle_path=failure_bundle_path,
    )


def run_pilot_batch_skeleton(
    *,
    config: RuntimePilotConfig,
    config_path: str | Path,
    plan_bundle: PilotPlanBundle,
    headless: bool = True,
    database_url: str | None = None,
) -> tuple[PilotBatchSummary, SchedulerBatchSummary]:
    batch_id = plan_bundle.metadata.batch_id or new_id("pilot_batch")
    store = LocalArtifactStore(config.external_paths.artifact_root)
    queue = build_scheduler_queue(plan_bundle.plans, SchedulerConfig(rate_limit_delay_seconds=config.tuning.screenshot_interval_seconds))

    batch_root = Path(config.external_paths.artifact_root).expanduser().resolve() / batch_id
    batch_root.mkdir(parents=True, exist_ok=True)
    batch_preflight_dir = batch_root / "batch-preflight"
    batch_preflight_dir.mkdir(parents=True, exist_ok=True)

    batch_manifest = PilotBatchManifest(
        batch_id=batch_id,
        account_alias=config.account_alias,
        runtime_config_path=str(Path(config_path).resolve()),
        runtime_config_fingerprint=_runtime_config_fingerprint(config_path),
        runner_version=__version__,
        artifact_root=str(config.external_paths.artifact_root),
        selected_course_count=len(plan_bundle.plans),
    )
    preflight_result = _run_auth_preflight_for_path(
        config=config,
        screenshot_dir=batch_preflight_dir,
        repo_root=Path.cwd(),
        account_alias=config.account_alias,
        headless=headless,
    )
    batch_preflight_path = write_model_json(batch_preflight_dir / "auth-preflight.json", preflight_result)

    run_manifests: list[PilotRunManifest] = []
    auth_failure_reasons = [preflight_result.status.value] if preflight_result.status != AuthPreflightStatus.AUTHENTICATED else []
    diagnostics_snapshot = _diagnostics_snapshot_from_preflight(preflight_result, config)

    if preflight_result.status != AuthPreflightStatus.AUTHENTICATED:
        queue = block_queue_for_auth(queue)
        batch_status = PilotBatchStatus.PREFLIGHT_FAILED
        for plan in plan_bundle.plans:
            layout = store.ensure_run_layout(batch_id=batch_id, run_id=new_id("pilot_run"), course_title=plan.course_title)
            planned_artifacts = _build_planned_artifacts(store, layout)
            run_manifest = _build_run_manifest(
                batch_id=batch_id,
                account_alias=config.account_alias,
                runtime_config_path=config_path,
                plan=plan,
                layout=layout,
                planned_artifacts=planned_artifacts,
                run_id=Path(layout.run_root).name.split("-", maxsplit=1)[0],
            ).model_copy(
                update={
                    "lifecycle_status": PilotRunStatus.BLOCKED_BY_AUTH,
                    "preflight_result_path": str(batch_preflight_path.resolve()),
                    "preflight_status": preflight_result.status.value,
                    "preflight_error_reason": preflight_result.error_reason,
                    "diagnostics_snapshot_path": str((Path(layout.diagnostics_dir) / "diagnostics-snapshot.json").resolve()),
                    "diagnostics_snapshot": diagnostics_snapshot,
                },
                deep=True,
            )
            write_model_json(Path(layout.diagnostics_dir) / "diagnostics-snapshot.json", diagnostics_snapshot)
            run_manifest = _reconcile_runtime_artifacts(
                run_manifest=run_manifest,
                preflight_result=preflight_result,
                diagnostics_path=Path(layout.diagnostics_dir) / "diagnostics-snapshot.json",
            )
            failure_bundle = _write_failure_bundle(
                run_manifest=run_manifest,
                stage=FailureStage.BATCH_PREFLIGHT,
                auth_preflight_result=preflight_result,
                diagnostics_snapshot=diagnostics_snapshot,
            )
            run_manifest = run_manifest.model_copy(update={"failure_bundle_path": str(_failure_bundle_path(layout).resolve())}, deep=True)
            _write_processing_manifest(run_manifest)
            _write_qa_report(run_manifest)
            run_manifest_path = write_model_json(_run_manifest_path(layout), run_manifest)
            run_manifest = run_manifest.model_copy(update={"run_manifest_path": str(run_manifest_path.resolve())}, deep=True)
            write_model_json(_run_manifest_path(layout), run_manifest)
            run_manifests.append(run_manifest)
    else:
        queue = mark_queue_ready_for_live_capture(queue)
        batch_status = PilotBatchStatus.READY_FOR_LIVE_CAPTURE
        for plan in plan_bundle.plans:
            layout = store.ensure_run_layout(batch_id=batch_id, run_id=new_id("pilot_run"), course_title=plan.course_title)
            planned_artifacts = _build_planned_artifacts(store, layout)
            run_manifest = _build_run_manifest(
                batch_id=batch_id,
                account_alias=config.account_alias,
                runtime_config_path=config_path,
                plan=plan,
                layout=layout,
                planned_artifacts=planned_artifacts,
                run_id=Path(layout.run_root).name.split("-", maxsplit=1)[0],
            ).model_copy(
                update={
                    "lifecycle_status": PilotRunStatus.READY_FOR_LIVE_CAPTURE,
                    "preflight_result_path": str(batch_preflight_path.resolve()),
                    "preflight_status": preflight_result.status.value,
                    "diagnostics_snapshot_path": str((Path(layout.diagnostics_dir) / "diagnostics-snapshot.json").resolve()),
                    "diagnostics_snapshot": diagnostics_snapshot,
                },
                deep=True,
            )
            write_model_json(Path(layout.diagnostics_dir) / "diagnostics-snapshot.json", diagnostics_snapshot)
            run_manifest = _reconcile_runtime_artifacts(
                run_manifest=run_manifest,
                preflight_result=preflight_result,
                diagnostics_path=Path(layout.diagnostics_dir) / "diagnostics-snapshot.json",
            )
            _write_processing_manifest(run_manifest)
            _write_qa_report(run_manifest)
            run_manifest_path = write_model_json(_run_manifest_path(layout), run_manifest)
            run_manifest = run_manifest.model_copy(update={"run_manifest_path": str(run_manifest_path.resolve())}, deep=True)
            write_model_json(_run_manifest_path(layout), run_manifest)
            run_manifests.append(run_manifest)

    batch_manifest = _update_batch_counts(
        batch_manifest.model_copy(
            update={
                "batch_status": batch_status,
                "batch_preflight_result_path": str(batch_preflight_path.resolve()),
            },
            deep=True,
        ),
        run_manifests,
    )
    write_model_json(_batch_manifest_path(batch_root), batch_manifest)

    qa_results = [evaluate_pilot_run_manifest(run_manifest=run_manifest) for run_manifest in run_manifests]
    persist_pilot_records(
        database_url=database_url,
        batch_manifest=batch_manifest,
        run_manifests=run_manifests,
        qa_results={run_manifest.run_id: qa_result for run_manifest, qa_result in zip(run_manifests, qa_results, strict=False)},
    )
    scheduler_summary = summarize_scheduler_results(
        queue=queue,
        qa_results=qa_results,
        auth_failure_reasons=auth_failure_reasons,
        config=SchedulerConfig(rate_limit_delay_seconds=config.tuning.screenshot_interval_seconds),
    )

    return (
        PilotBatchSummary(
            batch_manifest_path=str(_batch_manifest_path(batch_root).resolve()),
            status=batch_manifest.batch_status,
            counts=batch_manifest.counts,
            run_manifest_paths=batch_manifest.run_manifest_paths,
        ),
        scheduler_summary,
    )
