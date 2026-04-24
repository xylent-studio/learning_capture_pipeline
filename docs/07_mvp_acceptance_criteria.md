# MVP acceptance criteria

## MVP scope

Capture and reconstruct 10 high-value SeedTalent courses using a manual or semi-automated capture lab.

## Must produce per course

- raw screen/audio recording path
- screenshot folder path
- transcript segments
- OCR frames
- reconstructed course outline
- reconstructed lessons
- source-linked content chunks
- QA coverage report
- draft training summary
- draft quiz
- review records

## Search/RAG acceptance

- Search returns only approved chunks by default.
- Results include source timestamp/screenshot/video citations.
- Filters work for brand, jurisdiction, course, rights status, review status, and asset type.

## Training generation acceptance

- Generator uses approved chunks only.
- Generated modules include source chunk IDs.
- Generated modules start as `needs_review`.
- The UI/API blocks publishing until approved.

## Capture QA acceptance

- Course coverage report shows lessons detected vs. captured.
- Audio presence is checked.
- Long silence gaps are flagged.
- Low OCR/transcript confidence is flagged.
- Possible PII is flagged.
- Missing sections can be marked `needs_recapture`.

## Governance acceptance

- Unknown/restricted rights block generation.
- PII issues block generation.
- Review decisions are audited.
- Raw artifacts are not visible to general users.
