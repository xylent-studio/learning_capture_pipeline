from __future__ import annotations

import json

from som_seedtalent_capture.autopilot.qa import AutopilotQAResult
from som_seedtalent_capture.db import build_session_factory
from som_seedtalent_capture.db_models import PilotBatchRecord, PilotQaSummaryRecord, PilotRunRecord
from som_seedtalent_capture.pilot_manifests import PilotBatchManifest, PilotRunManifest


def persist_pilot_records(
    *,
    database_url: str | None,
    batch_manifest: PilotBatchManifest,
    run_manifests: list[PilotRunManifest],
    qa_results: dict[str, AutopilotQAResult],
) -> bool:
    session_factory = build_session_factory(database_url)
    if session_factory is None:
        return False

    with session_factory() as session:
        batch_record = session.get(PilotBatchRecord, batch_manifest.batch_id)
        if batch_record is None:
            batch_record = PilotBatchRecord(
                batch_id=batch_manifest.batch_id,
                account_alias=batch_manifest.account_alias,
                runtime_config_path=batch_manifest.runtime_config_path,
                runtime_config_fingerprint=batch_manifest.runtime_config_fingerprint,
                runner_version=batch_manifest.runner_version,
                artifact_root=batch_manifest.artifact_root,
                batch_status=batch_manifest.batch_status.value,
                selected_course_count=batch_manifest.selected_course_count,
            )
            session.add(batch_record)
        else:
            batch_record.batch_status = batch_manifest.batch_status.value
            batch_record.selected_course_count = batch_manifest.selected_course_count
            batch_record.updated_at = batch_manifest.updated_at

        for run_manifest in run_manifests:
            run_record = session.get(PilotRunRecord, run_manifest.run_id)
            if run_record is None:
                run_record = PilotRunRecord(
                    run_id=run_manifest.run_id,
                    batch_id=batch_manifest.batch_id,
                    capture_session_id=run_manifest.capture_session_id,
                    course_title=run_manifest.course_title,
                    source_url=run_manifest.source_url,
                    permission_basis=run_manifest.permission_basis,
                    rights_status=run_manifest.rights_status,
                    account_alias=run_manifest.account_alias,
                    lifecycle_status=run_manifest.lifecycle_status.value,
                    run_manifest_path=run_manifest.run_manifest_path or run_manifest.runtime_config_path,
                    qa_report_path=run_manifest.qa_report_path,
                    preflight_result_path=run_manifest.preflight_result_path,
                    preflight_status=run_manifest.preflight_status,
                    failure_bundle_path=run_manifest.failure_bundle_path,
                )
                session.add(run_record)
            else:
                run_record.lifecycle_status = run_manifest.lifecycle_status.value
                run_record.run_manifest_path = run_manifest.run_manifest_path or run_manifest.runtime_config_path
                run_record.qa_report_path = run_manifest.qa_report_path
                run_record.preflight_result_path = run_manifest.preflight_result_path
                run_record.preflight_status = run_manifest.preflight_status
                run_record.failure_bundle_path = run_manifest.failure_bundle_path
                run_record.updated_at = run_manifest.updated_at

            qa_result = qa_results.get(run_manifest.run_id)
            if qa_result is None:
                continue
            qa_record = session.get(PilotQaSummaryRecord, f"qa-summary-{run_manifest.run_id}")
            if qa_record is None:
                qa_record = PilotQaSummaryRecord(
                    qa_summary_id=f"qa-summary-{run_manifest.run_id}",
                    run_id=run_manifest.run_id,
                    readiness_status=qa_result.readiness_status.value,
                    recommended_status=qa_result.qa_report.recommended_status.value,
                    recapture_reasons=json.dumps([reason.value for reason in qa_result.recapture_reasons]),
                    warnings=json.dumps(qa_result.warnings),
                    qa_report_path=run_manifest.qa_report_path,
                )
                session.add(qa_record)
            else:
                qa_record.readiness_status = qa_result.readiness_status.value
                qa_record.recommended_status = qa_result.qa_report.recommended_status.value
                qa_record.recapture_reasons = json.dumps([reason.value for reason in qa_result.recapture_reasons])
                qa_record.warnings = json.dumps(qa_result.warnings)
                qa_record.qa_report_path = run_manifest.qa_report_path
        session.commit()
    return True
