# Ticket 001: Capture schema and migrations

Goal: Implement the capture-specific schema and model validation.

Context:
- docs/04_data_model.md
- src/som_seedtalent_capture/models.py
- migrations/001_initial_capture_schema.sql

Requirements:
- CaptureBatch, CaptureSession, CaptureEvent, VisualFrame, AudioTranscriptSegment, ReconstructedLesson, ContentChunk, CaptureQAReport.
- Enums for status, rights, PII, review, event type, chunk type.
- SQL migration aligned to models.
- Tests for required fields and default review/rights behavior.

Constraints:
- no production data
- no credentials
- no real SeedTalent content

Done when:
- pytest passes
- compileall passes
- migration and models are aligned
