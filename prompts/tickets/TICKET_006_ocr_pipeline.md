# Ticket 006: OCR pipeline

Goal: Process screenshots/keyframes into VisualFrame records.

Requirements:
- OCR provider interface
- fake OCR provider for tests
- confidence score
- source image URI/path preserved
- low-confidence frames flagged
- idempotent reprocessing

Done when:
- tests cover fake OCR and low-confidence behavior
