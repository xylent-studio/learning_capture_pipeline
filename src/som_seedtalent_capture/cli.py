from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from som_seedtalent_capture.models import CaptureBatch, CaptureEvent, CaptureEventType, CaptureQAReport, CaptureSession

app = typer.Typer(help="State of Mind SeedTalent authorized capture CLI scaffold.")
batch_app = typer.Typer(help="Capture batch commands.")
session_app = typer.Typer(help="Capture session commands.")
qa_app = typer.Typer(help="Capture QA commands.")
app.add_typer(batch_app, name="batch")
app.add_typer(session_app, name="session")
app.add_typer(qa_app, name="qa")
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
    """Create a capture batch record as JSON."""
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
    """Create a capture session record as JSON."""
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
    """Create an operator note event as JSON."""
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
    """Create a basic capture QA report as JSON."""
    report = CaptureQAReport(
        capture_session_id=capture_session_id,
        screenshot_count=screenshot_count,
        transcript_segment_count=transcript_segment_count,
        visual_frame_count=visual_frame_count,
        audio_detected=audio_detected,
    )
    write_json(out, report)
    console.print(f"Created QA report [bold]{report.qa_report_id}[/bold] -> {out}")


if __name__ == "__main__":
    app()
