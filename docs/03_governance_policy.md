# Governance policy

## Permission model

Each capture batch must include:

- permission basis
- scope
- operator
- source account
- capture date
- notes about exclusions

Default permission basis for this project:

```text
seedtalent_authorized_screen_capture
```

## Review model

All reconstructed and generated content starts as:

```text
needs_review
```

Allowed review states:

- needs_review
- approved
- rejected
- restricted
- needs_recapture
- pii_issue
- rights_issue

## Rights model

Allowed rights states:

- seedtalent_authorized_screen_capture
- state_of_mind_owned
- partner_owned_internal_use
- unknown
- restricted

Rules:

- `unknown` cannot be used for generation.
- `restricted` cannot be used for generation unless an explicit override policy exists.
- Partner/brand content must preserve owner/brand metadata.
- Generated training must cite source chunks.

## PII model

Allowed PII states:

- none_detected
- possible_pii
- contains_pii
- redacted
- approved_for_limited_use

Rules:

- possible/contains PII blocks broad search and generation.
- Learner analytics must be separate from content knowledge.
- Raw report screenshots should be admin-only.
- Do not embed raw employee identifiers.

## Audit requirements

Log every review decision:

- reviewer
- action
- timestamp
- target type
- target ID
- previous status
- new status
- notes

## Deletion and correction

The system must be able to remove or invalidate:

- raw artifacts
- processed frames
- transcripts
- OCR text
- chunks
- embeddings
- generated drafts

Use source IDs and capture_session_id to propagate deletions.
