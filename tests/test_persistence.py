from pathlib import Path

from som_seedtalent_capture.artifacts import ArtifactKind, LocalArtifactStore
from som_seedtalent_capture.autopilot.qa import AutopilotQAResult, AutopilotReadinessStatus
from som_seedtalent_capture.models import CaptureQAReport
from som_seedtalent_capture.pilot_manifests import BatchRunCounts, PilotBatchManifest, PilotBatchStatus, PilotRunManifest, PilotRunStatus
from som_seedtalent_capture.pilot_persistence import persist_pilot_records


def test_persist_pilot_records_round_trip(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'pilot.db').resolve()}"
    store = LocalArtifactStore(tmp_path / "artifacts")
    layout = store.ensure_run_layout(batch_id="batch-db", run_id="run-db", course_title="Pilot Course")
    planned_artifacts = [
        store.build_record(layout=layout, kind=ArtifactKind.QA_REPORT, name="qa-report", extension="json"),
        store.build_record(layout=layout, kind=ArtifactKind.PREFLIGHT_CAPTURE, name="auth-preflight", extension="png"),
    ]
    run_manifest_path = Path(layout.run_root) / "run-manifest.json"
    batch_manifest = PilotBatchManifest(
        batch_id="batch-db",
        account_alias="seedtalent-capture-bot",
        runtime_config_path=str(tmp_path / "runtime.yaml"),
        runtime_config_fingerprint="abcd1234",
        runner_version="0.1.0",
        artifact_root=str(tmp_path / "artifacts"),
        selected_course_count=1,
        batch_status=PilotBatchStatus.READY_FOR_LIVE_CAPTURE,
        counts=BatchRunCounts(ready_for_live_capture_count=1),
    )
    run_manifest = PilotRunManifest(
        run_id="run-db",
        batch_id="batch-db",
        capture_session_id="session-db",
        course_title="Pilot Course",
        source_url="https://app.seedtalent.com/courses/pilot-course",
        permission_basis="seedtalent_contract_full_use",
        rights_status="seedtalent_contract_full_use",
        account_alias="seedtalent-capture-bot",
        lifecycle_status=PilotRunStatus.READY_FOR_LIVE_CAPTURE,
        artifact_layout=layout,
        planned_artifacts=planned_artifacts,
        runtime_config_path=str(tmp_path / "runtime.yaml"),
        run_manifest_path=str(run_manifest_path),
        qa_report_path=planned_artifacts[0].local_path,
        preflight_result_path=planned_artifacts[1].local_path,
        preflight_status="authenticated",
    )
    qa_result = AutopilotQAResult(
        readiness_status=AutopilotReadinessStatus.READY_FOR_LIVE_CAPTURE,
        qa_report=CaptureQAReport(
            capture_session_id="session-db",
            recommended_status="needs_review",
        ),
        warnings=["runner_not_executed"],
    )

    persisted = persist_pilot_records(
        database_url=database_url,
        batch_manifest=batch_manifest,
        run_manifests=[run_manifest],
        qa_results={run_manifest.run_id: qa_result},
    )

    assert persisted is True
    assert Path(tmp_path / "pilot.db").exists()
