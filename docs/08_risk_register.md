# Risk register

## Risk: audio capture fails silently

Mitigation:

- mandatory 10-second test recording
- audio-level detection
- QA flag for silence gaps

## Risk: OCR misses key text

Mitigation:

- slow scrolling SOP
- screenshot interval plus event screenshots
- OCR confidence thresholds
- human review of low-confidence frames

## Risk: course flow is incomplete

Mitigation:

- lesson checklist
- QA coverage report
- operator notes
- recapture workflow

## Risk: employee PII enters content index

Mitigation:

- separate learner analytics from content chunks
- PII detection
- default blocking of possible/contains PII
- no raw employee identifiers in embeddings

## Risk: Codex builds disallowed scraping functionality

Mitigation:

- AGENTS.md do-not rules
- code review checklist
- tests and review prompts
- local skills with explicit boundaries

## Risk: generated training overstates source content

Mitigation:

- source citations required
- generated drafts only
- human review before publishing
- retrieval limited to approved chunks

## Risk: capture artifacts are too large

Mitigation:

- object storage lifecycle rules
- artifact retention policy
- derived artifact cleanup
- content hashes and deduplication

## Risk: state-specific cannabis guidance is mixed incorrectly

Mitigation:

- jurisdiction required where known
- filters by jurisdiction
- reviewer approval for compliance content
- no generated compliance module from unlabeled chunks
