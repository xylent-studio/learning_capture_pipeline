# Ticket 011: Search API

Goal: Implement approved-chunk search.

Requirements:
- keyword search first
- vector interface with fake embeddings in tests
- filters: brand, jurisdiction, course, rights_status, review_status, asset_type
- approved-only default
- citations included in response

Done when:
- tests prove restricted/unapproved chunks are excluded by default
