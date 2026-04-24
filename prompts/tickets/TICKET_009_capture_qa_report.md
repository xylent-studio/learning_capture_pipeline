# Ticket 009: Capture QA report

Goal: Generate capture quality and coverage reports.

Report:
- duration
- audio presence
- screenshot count
- transcript segment count
- OCR frame count
- low-confidence transcript/OCR counts
- silence gaps if available
- possible PII flags if available
- recommended status

Done when:
- tests cover good capture, missing audio, low OCR, and needs_recapture recommendation
