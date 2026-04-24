# Ticket 012: Draft training generator

Goal: Generate draft internal training outputs from approved chunks.

Formats:
- module
- quiz
- flashcards
- SOP checklist
- roleplay
- manager coaching guide

Rules:
- approved chunks only
- source citations required
- generated output starts as needs_review
- publish is blocked until human approval

Done when:
- tests prove unapproved/restricted/PII chunks are excluded
- generated object has source_chunk_ids and review_status needs_review
