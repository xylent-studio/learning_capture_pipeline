---
name: rag-training-generator
description: Use when building search, retrieval, embeddings, citations, and draft-only training generation from approved SeedTalent capture chunks.
---

# RAG training generator skill

## Purpose

Build source-linked retrieval and draft training generation for internal State of Mind training.

## Rules

- Retrieve approved chunks only by default.
- Include source chunk IDs and citations in every generated output.
- Filter by role, topic, jurisdiction, brand, rights status, and review status.
- Do not generate compliance guidance from unlabeled or unapproved chunks.
- Generated output starts as `needs_review`.
- Use fake embeddings in tests.

## Done checklist

- restricted/unapproved chunks are excluded
- citations are present
- generated modules are not publishable by default
- tests cover filters and review gates
