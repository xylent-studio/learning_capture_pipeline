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
from som_seedtalent_capture.autopilot.qa import AutopilotQAResult, evaluate_pilot_run_manifest
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
from som_seedtalent_capture.auth import AuthPreflightResult, AuthPreflightStatus, PlaywrightVisibleAuthPreflight, run_auth_preflight
from som_seedtalent_capture.config import PilotCourseSelection, RuntimePilotConfig
from som_seedtalent_capture.models import new_id
from som_seedtalent_capture.permissions import PermissionManifest, authorize_capture
from som_seedtalent_capture.pilot_manifests import (
    BatchRunCounts,
    FailureBundle,
    FailureStage,
    PilotBatchManifest,
    PilotBatchStatus,
    PilotBatchSummary,
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
        current_url=result.current_url,
        visible_state_summary=result.visible_state_summary,
        screenshot_uri=result.screenshot_uri,
        prohibited_path_detected=result.prohibited_path_detected,
        prohibited_path_hits=hits,
        notes=notes,
    )


def _suggest_next_action(result: AuthPreflightResult) -> str:
    if result.status == AuthPreflightStatus.AUTH_EXPIRED:
        return "Refresh the headed browser session and save a new external storage-state file."
    if result.status == AuthPreflightStatus.PROHIBITED_PATH:
        return "Return to the approved SeedTalent training scope before retrying the pilot."
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
        error_type=error_type,
        error_message=error_message,
        auth_preflight_result=auth_preflight_result.model_dump(mode="json") if auth_preflight_result is not None else None,
        prohibited_path_hits=diagnostics_snapshot.prohibited_path_hits if diagnostics_snapshot else [],
        diagnostics_snapshot=diagnostics_snapshot,
        suggested_next_action=_suggest_next_action(auth_preflight_result) if auth_preflight_result is not None else "Inspect the diagnostics snapshot and retry safely.",
    )
    path = _failure_bundle_path(run_manifest.artifact_layout)
    write_model_json(path, bundle)
    return bundle


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
