# Ticket 008: Reconstruction engine

Goal: Merge events, OCR, transcript, and notes into reconstructed lessons and content chunks.

Requirements:
- group by lesson markers where available
- fallback to timestamp/page-title heuristics
- every content chunk has timestamp or screenshot citation
- all chunks default to needs_review
- no generated publication state

Done when:
- tests prove citations are required
- tests prove review_status defaults to needs_review
