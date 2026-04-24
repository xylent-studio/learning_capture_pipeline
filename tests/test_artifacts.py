from pathlib import Path

from som_seedtalent_capture.artifacts import ArtifactKind, LocalArtifactStore


def test_local_artifact_store_creates_expected_layout_and_records(tmp_path: Path):
    store = LocalArtifactStore(tmp_path / "artifacts")

    layout = store.ensure_run_layout(
        batch_id="batch-001",
        run_id="run-001",
        course_title="Pilot Course",
    )
    record = store.build_record(
        layout=layout,
        kind=ArtifactKind.SCREEN_RECORDING,
        name="Main Recording",
        extension=".mp4",
    )

    assert Path(layout.recordings_dir).exists()
    assert Path(layout.screenshots_dir).exists()
    assert Path(layout.preflight_dir).exists()
    assert Path(layout.qa_dir).exists()
    assert Path(layout.processing_dir).exists()
    assert Path(layout.diagnostics_dir).exists()
    assert record.local_path.endswith("main-recording.mp4")
    assert record.relative_path.startswith("batch-001")


def test_local_artifact_store_slugifies_empty_names(tmp_path: Path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    layout = store.ensure_run_layout(
        batch_id="batch-002",
        run_id="run-002",
        course_title="Pilot Course",
    )

    record = store.build_record(
        layout=layout,
        kind=ArtifactKind.DIAGNOSTIC_SNAPSHOT,
        name="!!!",
        extension="json",
    )

    assert record.local_path.endswith("artifact.json")
