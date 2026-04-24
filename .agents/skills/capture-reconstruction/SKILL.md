---
name: capture-reconstruction
description: Use when transforming OCR, screenshots, transcripts, keyframes, events, and notes into reconstructed courses, lessons, and source-linked content chunks.
---

# Capture reconstruction skill

## Purpose

Build deterministic, auditable reconstruction workflows from captured media.

## Inputs

- capture events
- visual frames
- OCR text
- transcript segments
- screenshots
- raw recording timestamp ranges
- operator notes

## Outputs

- reconstructed lessons
- summaries
- learning objectives
- content chunks
- source citations

## Rules

- Every chunk must cite timestamp and/or screenshot.
- Every chunk starts as `needs_review`.
- Do not infer unsupported facts.
- Preserve brand, jurisdiction, capture_session_id, and source URL metadata.
- Use confidence scores and flag low-confidence areas.

## Done checklist

- chunks have source citations
- low-confidence chunks are flagged
- reconstruction can be rerun idempotently
- tests cover ordering and citation behavior
