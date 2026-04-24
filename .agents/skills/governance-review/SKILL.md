---
name: governance-review
description: Use when implementing rights, PII, review status, approval workflow, audit logs, deletion propagation, and generation-blocking rules.
---

# Governance review skill

## Purpose

Ensure the pipeline is safe for employee data, partner/brand content, and human-reviewed training creation.

## Rules

- Unknown rights block generation.
- Restricted rights block generation unless an explicit override exists.
- Possible or confirmed PII blocks general search and generation.
- Generated outputs default to `needs_review`.
- Human review is required before publishing.
- Every decision must be audited.
- Learner analytics stay separate from training content.

## Done checklist

- tests prove blocking behavior
- audit records are written
- no bypass path exists in API or UI
- list views do not expose raw PII
