---
name: capture-qa
description: Use when building capture coverage reports, quality checks, recapture workflow, transcript/OCR confidence checks, silence detection, and PII flags.
---

# Capture QA skill

## Purpose

Help reviewers know whether a SeedTalent capture session is complete and usable.

## Report fields

- duration captured
- audio detected yes/no
- transcript coverage
- OCR coverage
- screenshot count
- lesson coverage
- long silence gaps
- low-confidence transcript sections
- low-confidence OCR sections
- possible PII
- needs recapture reasons

## Rules

- QA reports should never mark content approved.
- QA can recommend `needs_recapture` or `needs_review`.
- Low confidence should be visible to reviewers.
- Do not expose raw employee PII in broad dashboards.

## Done checklist

- fake captures can generate QA reports
- silence/coverage thresholds are configurable
- results are deterministic enough for tests
