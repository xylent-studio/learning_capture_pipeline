# Ticket 002: Local JSON capture store

Goal: Add a simple local persistence layer for MVP capture sessions before the database layer is built.

Requirements:
- create batch/session folders under CAPTURE_ARTIFACT_ROOT
- write batch.json, session.json, events.jsonl, qa_report.json
- append events idempotently where possible
- never write outside artifact root
- tests for safe paths

Done when:
- CLI can create a batch and session locally
- tests pass with tmp_path
