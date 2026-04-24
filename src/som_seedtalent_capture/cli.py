from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console

from som_seedtalent_capture.auth import PlaywrightVisibleAuthPreflight, run_auth_preflight
from som_seedtalent_capture.config import load_pilot_course_selection, load_runtime_pilot_config, validate_runtime_pilot_paths
from som_seedtalent_capture.models import CaptureBatch, CaptureEvent, CaptureEventType, CaptureQAReport, CaptureSession
from som_seedtalent_capture.pilot_runtime import (
    build_capture_plans_from_selection,
    build_pilot_plan_bundle,
    load_pilot_plan_bundle,
    prepare_auth_bootstrap,
    run_pilot_batch_skeleton,
    run_pilot_course_skeleton,
    run_visible_catalog_discovery,
)
from som_seedtalent_capture.runtime_manifest import FileSystemRuntimeManifestLoader, validate_runtime_manifest_path
from som_seedtalent_capture.scheduler import SchedulerConfig, build_scheduler_queue, summarize_scheduler_results

app = typer.Typer(help="State of Mind SeedTalent authorized capture CLI scaffold.")
batch_app = typer.Typer(help="Capture batch commands.")
session_app = typer.Typer(help="Capture session commands.")
qa_app = typer.Typer(help="Capture QA commands.")
pilot_app = typer.Typer(help="Pre-login and pilot-readiness commands.")
scheduler_app = typer.Typer(help="Scheduler skeleton commands.")
app.add_typer(batch_app, name="batch")
app.add_typer(session_app, name="session")
app.add_typer(qa_app, name="qa")
app.add_typer(pilot_app, name="pilot")
app.add_typer(scheduler_app, name="scheduler")
console = Console()


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(obj, "model_dump"):
        payload = obj.model_dump(mode="json")
    else:
        payload = obj
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@batch_app.command("create")
def create_batch(
    scope: str = typer.Option(..., "--scope", help="Human-readable capture scope."),
    operator: str = typer.Option(..., "--operator", help="Capture operator name or internal ID."),
    out: Path = typer.Option(Path("capture_batch.json"), "--out", help="Output JSON path."),
) -> None:
    batch = CaptureBatch(scope_description=scope, operator=operator)
    write_json(out, batch)
    console.print(f"Created capture batch [bold]{batch.capture_batch_id}[/bold] -> {out}")


@session_app.command("start")
def start_session(
    capture_batch_id: str = typer.Option(..., "--batch-id"),
    course_title: str | None = typer.Option(None, "--course-title"),
    source_url: str | None = typer.Option(None, "--source-url"),
    brand: str | None = typer.Option(None, "--brand"),
    jurisdiction: str | None = typer.Option(None, "--jurisdiction"),
    out: Path = typer.Option(Path("capture_session.json"), "--out"),
) -> None:
    session = CaptureSession(
        capture_batch_id=capture_batch_id,
        course_title=course_title,
        source_url=source_url,
        brand=brand,
        jurisdiction=jurisdiction,
    )
    write_json(out, session)
    console.print(f"Created capture session [bold]{session.capture_session_id}[/bold] -> {out}")


@session_app.command("note")
def add_note(
    capture_session_id: str = typer.Option(..., "--session-id"),
    timestamp_ms: int = typer.Option(..., "--timestamp-ms"),
    note: str = typer.Option(..., "--note"),
    out: Path = typer.Option(Path("capture_event_note.json"), "--out"),
) -> None:
    event = CaptureEvent(
        capture_session_id=capture_session_id,
        event_type=CaptureEventType.NOTE,
        timestamp_ms=timestamp_ms,
        operator_note=note,
    )
    write_json(out, event)
    console.print(f"Created note event [bold]{event.event_id}[/bold] -> {out}")


@qa_app.command("report")
def qa_report(
    capture_session_id: str = typer.Option(..., "--session-id"),
    screenshot_count: int = typer.Option(0, "--screenshots"),
    transcript_segment_count: int = typer.Option(0, "--transcript-segments"),
    visual_frame_count: int = typer.Option(0, "--visual-frames"),
    audio_detected: bool | None = typer.Option(None, "--audio-detected/--audio-not-detected"),
    out: Path = typer.Option(Path("qa_report.json"), "--out"),
) -> None:
    report = CaptureQAReport(
        capture_session_id=capture_session_id,
        screenshot_count=screenshot_count,
        transcript_segment_count=transcript_segment_count,
        visual_frame_count=visual_frame_count,
        audio_detected=audio_detected,
    )
    write_json(out, report)
    console.print(f"Created QA report [bold]{report.qa_report_id}[/bold] -> {out}")


@pilot_app.command("validate-config")
def validate_config(
    config_path: Path = typer.Option(..., "--config"),
    out: Path = typer.Option(Path("runtime_config_validation.json"), "--out"),
) -> None:
    config = load_runtime_pilot_config(config_path)
    repo_root = Path.cwd()
    validation = {
        "seedtalent_base_url": config.seedtalent_base_url,
        "account_alias": config.account_alias,
        "auth_mode": config.auth_mode.value,
        **validate_runtime_pilot_paths(config, repo_root),
    }
    write_json(out, validation)
    console.print(f"Validated runtime config -> {out}")


@pilot_app.command("bootstrap-auth")
def bootstrap_auth(
    config_path: Path = typer.Option(..., "--config"),
    out: Path = typer.Option(Path("auth_bootstrap.json"), "--out"),
) -> None:
    config = load_runtime_pilot_config(config_path)
    preparation = prepare_auth_bootstrap(config)
    write_json(out, preparation)
    console.print(f"Prepared auth bootstrap paths for [bold]{config.account_alias}[/bold] -> {out}")


@pilot_app.command("auth-preflight")
def auth_preflight(
    config_path: Path = typer.Option(..., "--config"),
    out: Path = typer.Option(Path("auth_preflight.json"), "--out"),
    headless: bool = typer.Option(True, "--headless/--headed"),
) -> None:
    config = load_runtime_pilot_config(config_path)
    browser_preflight = PlaywrightVisibleAuthPreflight(
        screenshot_dir=config.external_paths.auth_screenshot_dir,
        authenticated_indicators=config.tuning.authenticated_indicators,
        auth_expired_indicators=config.tuning.auth_expired_indicators,
        prohibited_path_patterns=config.tuning.prohibited_path_patterns,
        headless=headless,
    )
    result = run_auth_preflight(
        mode=config.auth_mode,
        storage_state_path=config.external_paths.storage_state_path,
        base_url=config.seedtalent_base_url,
        browser_preflight=browser_preflight,
        repo_root=Path.cwd(),
        account_alias=config.account_alias,
        allowed_storage_root=config.external_paths.secret_root,
    )
    write_json(out, result)
    console.print(f"Ran auth preflight for [bold]{config.account_alias}[/bold] -> {out}")


@pilot_app.command("discovery")
def pilot_discovery(
    config_path: Path = typer.Option(..., "--config"),
    out: Path = typer.Option(Path("catalog_discovery.json"), "--out"),
    headless: bool = typer.Option(True, "--headless/--headed"),
) -> None:
    config = load_runtime_pilot_config(config_path)
    manifest = FileSystemRuntimeManifestLoader().load(
        manifest_path=config.external_paths.permission_manifest_path,
        repo_root=Path.cwd(),
        secret_root=config.external_paths.secret_root,
    )
    discovery = run_visible_catalog_discovery(config=config, manifest=manifest, headless=headless)
    write_json(out, discovery)
    console.print(f"Discovered catalog inventory -> {out}")


@pilot_app.command("plans-from-approved")
def plans_from_approved(
    config_path: Path = typer.Option(..., "--config"),
    out: Path = typer.Option(Path("approved_capture_plans.json"), "--out"),
    approved_courses_path: Path | None = typer.Option(None, "--approved-courses"),
) -> None:
    config = load_runtime_pilot_config(config_path)
    selection_path = approved_courses_path or config.external_paths.approved_courses_path
    manifest = FileSystemRuntimeManifestLoader().load(
        manifest_path=config.external_paths.permission_manifest_path,
        repo_root=Path.cwd(),
        secret_root=config.external_paths.secret_root,
    )
    selection = load_pilot_course_selection(selection_path)
    plans = build_capture_plans_from_selection(selection=selection, config=config, manifest=manifest)
    write_json(out, build_pilot_plan_bundle(selection=selection, config=config, plans=plans))
    console.print(f"Built capture plans from approved courses -> {out}")


@pilot_app.command("run-course")
def run_course(
    config_path: Path = typer.Option(..., "--config"),
    plan_bundle_path: Path = typer.Option(..., "--plan-bundle"),
    course_url: str | None = typer.Option(None, "--course-url"),
    out: Path = typer.Option(Path("pilot_run_summary.json"), "--out"),
    headless: bool = typer.Option(True, "--headless/--headed"),
) -> None:
    config = load_runtime_pilot_config(config_path)
    FileSystemRuntimeManifestLoader().load(
        manifest_path=config.external_paths.permission_manifest_path,
        repo_root=Path.cwd(),
        secret_root=config.external_paths.secret_root,
    )
    summary = run_pilot_course_skeleton(
        config=config,
        config_path=config_path,
        plan_bundle=load_pilot_plan_bundle(plan_bundle_path),
        course_url=course_url,
        headless=headless,
        database_url=os.environ.get("DATABASE_URL"),
    )
    write_json(out, summary)
    console.print(f"Built pilot run skeleton -> {out}")


@pilot_app.command("run-batch")
def run_batch(
    config_path: Path = typer.Option(..., "--config"),
    plan_bundle_path: Path = typer.Option(..., "--plan-bundle"),
    out: Path = typer.Option(Path("pilot_batch_summary.json"), "--out"),
    headless: bool = typer.Option(True, "--headless/--headed"),
) -> None:
    config = load_runtime_pilot_config(config_path)
    FileSystemRuntimeManifestLoader().load(
        manifest_path=config.external_paths.permission_manifest_path,
        repo_root=Path.cwd(),
        secret_root=config.external_paths.secret_root,
    )
    batch_summary, scheduler_summary = run_pilot_batch_skeleton(
        config=config,
        config_path=config_path,
        plan_bundle=load_pilot_plan_bundle(plan_bundle_path),
        headless=headless,
        database_url=os.environ.get("DATABASE_URL"),
    )
    write_json(
        out,
        {
            "batch_summary": batch_summary.model_dump(mode="json"),
            "scheduler_summary": scheduler_summary.model_dump(mode="json"),
        },
    )
    console.print(f"Built pilot batch skeleton -> {out}")


@scheduler_app.command("dry-run")
def scheduler_dry_run(
    config_path: Path = typer.Option(..., "--config"),
    out: Path = typer.Option(Path("scheduler_summary.json"), "--out"),
    approved_courses_path: Path | None = typer.Option(None, "--approved-courses"),
) -> None:
    config = load_runtime_pilot_config(config_path)
    selection_path = approved_courses_path or config.external_paths.approved_courses_path
    manifest_path = validate_runtime_manifest_path(config.external_paths.permission_manifest_path, Path.cwd())
    selection = load_pilot_course_selection(selection_path)
    manifest = FileSystemRuntimeManifestLoader().load(
        manifest_path=manifest_path,
        repo_root=Path.cwd(),
        secret_root=config.external_paths.secret_root,
    )
    plans = build_capture_plans_from_selection(selection=selection, config=config, manifest=manifest)
    queue = build_scheduler_queue(plans, SchedulerConfig(rate_limit_delay_seconds=config.tuning.screenshot_interval_seconds))
    summary = summarize_scheduler_results(
        queue=queue,
        qa_results=[],
        auth_failure_reasons=[],
        config=SchedulerConfig(rate_limit_delay_seconds=config.tuning.screenshot_interval_seconds),
    )
    write_json(out, summary)
    console.print(f"Built scheduler dry-run summary -> {out}")


if __name__ == "__main__":
    app()
