# Ticket 007: Transcript pipeline

Goal: Extract/transcribe captured audio into timestamped segments.

Requirements:
- audio extraction command interface
- speech-to-text provider interface
- fake provider for tests
- timestamped AudioTranscriptSegment records
- confidence where available
- idempotent reprocessing

Done when:
- tests cover fake transcript and required source metadata
