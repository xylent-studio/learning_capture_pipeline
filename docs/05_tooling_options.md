# Tooling options

## Capture

Recommended initial approach:

- Manual browser capture + OBS or FFmpeg.
- Screenshot interval capture from CLI/Playwright.
- Operator notes for ambiguous screens.

Later automation:

- Playwright headed runner for repeatable navigation.
- Persistent browser storage state outside repo.
- Local fake HTML course fixtures for testing.

## Recording

Options:

- OBS: easiest operator workflow, strong screen/audio support.
- FFmpeg: scriptable and lightweight, but platform-specific audio setup can be tricky.
- Playwright video: useful for browser viewport recording but not sufficient alone for system audio.

## OCR

Use a provider interface. Initial options:

- local OCR for cheap/high-volume processing
- cloud OCR for difficult screenshots
- vision model for layout-heavy pages, charts, labels, and slides

## Speech-to-text

Use a provider interface. Requirements:

- timestamped segments
- confidence where available
- retry/idempotency
- fake provider in tests

## Storage

- S3-compatible object storage for raw and processed artifacts.
- MinIO for local dev.
- Never commit raw recordings or screenshots.

## Database

- Postgres for metadata.
- pgvector for initial embeddings.
- Separate content chunks from learner analytics.

## Workers

Start simple:

- synchronous CLI jobs for MVP
- later move to Celery/RQ/Prefect/Dagster once processing volume increases

## Search/RAG

- keyword search first
- pgvector embeddings second
- filters by jurisdiction, brand, rights, review status, capture session, source course
- answer generation only from approved chunks

## Codex

Use Codex for:

- repo scaffolding
- data models
- migrations
- CLI
- processing workers
- fake providers/tests
- review dashboard
- API endpoints
- PR review
- security review

Do not use Codex to store or handle production SeedTalent credentials.
