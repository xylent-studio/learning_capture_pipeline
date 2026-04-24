# AGENTS.md

## Mandatory re-entry

Before meaningful work in this workspace on a machine that has the local intel workspace, run:

`.\scripts\rehydrate-agent.ps1`

If you already know the work theme, pass a trigger so routed recall lands on the right surfaces immediately:

`.\scripts\rehydrate-agent.ps1 -Trigger "governance rights and auth"`

Do not skip re-entry for autonomy, permissions, capture workflow, reconstruction, storage, or training-generation work unless the task is truly trivial.

Trusted external context packs for this project can be dropped into:

`C:\dev\_intel\incoming-context\learning-capture-pipeline\pending`

The local machine loop will ingest them automatically, preserve the raw source, and expose only distilled supplemental context through re-entry surfaces.

## Project identity

This repository builds State of Mind's authorized SeedTalent screen-capture and multimodal training reconstruction pipeline.

SeedTalent has granted permission for screen capture, but it is not providing backend access or APIs. Build a controlled capture lab and reconstruction pipeline. Do not build a backend scraper.

## Permission stance for this repo

State of Mind has represented that SeedTalent and relevant vendors have contractually authorized State of Mind to use the covered SeedTalent-hosted content for this development effort, including capture and derivative internal training use. Treat this as an explicit project fact.

Do not block implementation because of generic rights uncertainty when a capture batch has `permission_basis=seedtalent_contract_full_use` and the content is inside the permission manifest. Rights controls are implementation metadata and audit proof, not a refusal mechanism.

Raise a rights/scope issue only when:

- the content is outside the approved SeedTalent account or capture scope,
- the course/vendor is not listed in the permission manifest and no broad permission applies,
- the capture includes account, billing, private messages, or unrelated user data,
- PII is captured in a way that should not enter embeddings or generated training, or
- the implementation would use backend APIs, hidden endpoints, network interception, or access-control bypass instead of approved visible-UI capture.

## Workspace split to preserve

This workspace is distinct from `C:\dev\State of Mind\SeedTalent`.

Use this workspace for:

- authorized SeedTalent capture engineering
- reconstruction pipeline work
- autonomy, QA, permissions, and governed training generation

Use `C:\dev\State of Mind\SeedTalent` for:

- `itssom.com` audit/remediation work
- website findings
- reusable site-review learning

## Canonical source-control posture

Canonical local root:

`C:\dev\Learning Capture Pipeline`

Canonical GitHub repo:

`https://github.com/xylent-studio/learning_capture_pipeline`

Default branch:

`main`

Keep this workspace at its current local path so `_intel` continuity mappings, restore anchors, and checkpoints remain attached to the same root.

The canonical GitHub repo is public by explicit choice. Treat that as an operational constraint, not a suggestion.

Do not commit:

- real permission manifests
- production or runtime credentials
- Playwright storage state
- raw capture artifacts
- imported external context packs
- real SeedTalent content
- employee PII

Use example manifests only in repo-tracked config, keep runtime auth state in ignored local storage, and keep raw captures out of git.

## Full-autonomy objective

The end goal is autonomous capture, not a manual capture tool. Manual workflows are calibration and fallback paths only. Build toward an autopilot that can authenticate safely, discover courses through visible UI, plan captures, navigate lessons, record screen/audio, capture screenshots and visible DOM text, handle videos/static pages/quizzes/reports, generate QA reports, enqueue recaptures, and hand humans only exceptions.

## Core objective

Capture video, audio, images, screenshots, visible text, quiz screens, reports, course structure, and interaction flow from authorized SeedTalent sessions. Convert captured material into State of Mind's governed internal training knowledge base and draft training generation system.

## Allowed implementation patterns

- Human-guided SeedTalent capture through a normal browser session.
- Headed browser automation that mimics approved user navigation.
- Screen recording via OBS, FFmpeg, or platform-native tools.
- System/browser audio recording.
- Screenshots at intervals and on events.
- OCR on screenshots and keyframes.
- Speech-to-text on captured audio.
- Keyframe extraction.
- Operator notes and capture metadata.
- UI-visible report downloads if exposed in the normal user interface.
- Local fake HTML fixtures for tests.

## Disallowed implementation patterns

- No backend API probing.
- No hidden endpoint discovery.
- No network interception.
- No reverse engineering SeedTalent software.
- No bypassing access controls.
- No credential sharing.
- No automated login using production secrets in code; approved runtime login may use a credential vault or persisted storage state outside the repo.
- No SeedTalent credentials in repo, prompts, tests, logs, or fixtures.
- No real SeedTalent content in tests or fixtures.
- No employee PII in tests, fixtures, logs, embeddings, or generated content.
- No generated content published without human review.

## Durable product rules

- Every capture session must have a permission basis; in-scope autonomous runs should default to `seedtalent_contract_full_use`.
- Every reconstructed chunk must cite a source timestamp, screenshot, or transcript segment.
- Every chunk starts as `needs_review`.
- Every generated training module starts as `needs_review`.
- Unknown rights status blocks generation, but `seedtalent_contract_full_use` and other manifest-authorized statuses are eligible after QA/review rules pass.
- PII issues block training generation until reviewed.
- Learner/report analytics must be separated from training content.
- Store raw capture artifacts in object storage or a local artifact folder; store only paths/metadata in the database.
- Keep jurisdiction, brand, owner, capture session, and version metadata attached to every chunk.

## Suggested stack

- Python for workers and CLI.
- FastAPI for service APIs.
- Pydantic for schemas.
- SQLAlchemy + Alembic for database access and migrations.
- Postgres + pgvector for metadata and initial vector search.
- S3-compatible object storage; MinIO for local development.
- Playwright for headed browser capture orchestration.
- OBS or FFmpeg for screen/audio recording.
- OCR provider behind an interface.
- Speech-to-text provider behind an interface.
- Next.js or React for review dashboard.
- pytest for tests.

## Current scaffold

The starter package contains Pydantic models and a minimal CLI. It is not a complete app. Use the docs and prompts to build iteratively.

## Required engineering practices

- Keep changes small and reviewable.
- Use one branch per ticket.
- Add or update tests for every parser, worker, API, and data model change.
- Use dependency injection for external providers such as OCR, speech-to-text, embeddings, storage, and LLM calls.
- Do not hardcode provider credentials.
- Use fake providers in tests.
- Include failure logging and idempotency for processing jobs.
- Include audit logs for review decisions.

## Done means

For each task, report:

- files changed
- behavior added
- tests run
- assumptions made
- privacy/security implications
- remaining risks or unvalidated behavior

Before finishing a task, run the relevant subset of:

```bash
pytest
python -m compileall src
```

After more tooling is added, also run:

```bash
ruff check .
ruff format --check .
mypy src
```

## Code review checklist

Check for:

- credential leakage
- real SeedTalent content accidentally committed
- real employee PII accidentally committed
- rights/review bypasses
- generated content marked publishable by default
- unrestricted use of unapproved chunks
- unsafe file path handling
- missing source citations
- missing idempotency
- missing audit logging

## How to prompt Codex for this repo

Use this format:

```text
Goal: <what to build>
Context: <files/docs that matter>
Constraints: follow AGENTS.md, no backend/API scraping, no credentials, no real data, all generated content needs review.
Done when: <specific tests/behavior/docs>
```

For complex tasks, use Plan mode first and ask Codex to challenge assumptions before coding.
