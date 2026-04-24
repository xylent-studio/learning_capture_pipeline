# Architecture

## System flow

```text
Authorized SeedTalent user account
  -> capture station
  -> headed browser session
  -> screen/audio recorder
  -> screenshots + event logger + operator notes
  -> raw artifact store
  -> processing workers
       -> audio extraction
       -> speech transcription
       -> keyframe extraction
       -> OCR
       -> image captioning/entity tagging later
  -> reconstruction engine
       -> course outline
       -> lessons
       -> transcript/OCR chunks
       -> source citations
  -> governance layer
       -> rights status
       -> PII status
       -> jurisdiction
       -> review status
       -> audit log
  -> approved search/RAG layer
  -> draft training generator
  -> human review
  -> internal training publishing
```

## Main services

### Capture API

Creates capture batches, capture sessions, events, notes, and artifact records.

### Capture CLI

Local operator-facing commands for creating sessions, taking screenshots, adding notes, and launching/ending recorder processes.

### Browser capture runner

A headed Playwright runner that can start a normal browser session, persist approved storage state outside the repo, capture URL/title/page events, and take screenshots. It must not inspect network traffic or call hidden APIs.

### Recorder worker

Starts/stops OBS or FFmpeg. Records screen and audio. Writes paths and metadata to capture_session.

### Processing API/workers

Runs OCR, transcription, keyframe extraction, content chunking, embeddings, and reconstruction jobs.

### Reconstruction engine

Merges transcript segments, OCR frames, click/page events, screenshots, and operator notes into course/lesson structure.

### Review dashboard

Allows humans to approve, reject, restrict, mark needs-recapture, mark PII issue, or mark rights issue.

### Search API

Hybrid keyword/vector retrieval over approved content chunks with filters for brand, jurisdiction, course, rights status, review status, and asset type.

### Training generator API

Generates draft-only training modules/quizzes/flashcards/checklists/roleplays from approved chunks only.

## Capture lab principle

This is closer to a controlled content QA lab than a scraper. The operator may manually guide the browser while the system records and reconstructs. Automation is added only after manual capture proves reliable.

## Recommended deployment stages

1. Local single-machine capture lab.
2. Local artifact-root capture plus local processing + review dashboard.
3. Optional object storage and Postgres once live capture is stable.
4. Team review workflow.
5. Semi-automated capture for repeatable course flows.
6. Analytics and training recommendation layer.
