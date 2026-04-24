# State of Mind SeedTalent Capture Pipeline

This repository is the kickoff scaffold for State of Mind's authorized SeedTalent screen-capture and multimodal training reconstruction pipeline.

## Mission

State of Mind has permission from SeedTalent to capture the SeedTalent user experience by screen capture, but SeedTalent is not providing backend access or APIs. This project therefore builds a governed capture lab and reconstruction system:

1. Capture authorized SeedTalent sessions through normal browser use.
2. Record screen, audio, screenshots, page metadata, and operator notes.
3. Transcribe audio, OCR screenshots/keyframes, and reconstruct courses/lessons.
4. Store source-linked chunks with rights, PII, jurisdiction, and review status.
5. Build an approved internal training knowledge base.
6. Generate draft internal training modules, quizzes, flashcards, coaching guides, SOP checklists, and roleplays.
7. Require human review before anything becomes publishable.

## Local continuity front door

On a machine that has the local `_intel` workspace, start meaningful work here:

`.\scripts\rehydrate-agent.ps1`

That refreshes the local continuity surfaces for this project before broad reading.

This workspace is separate from `C:\dev\State of Mind\SeedTalent`, which currently owns the `itssom.com` audit/remediation work. Do not collapse those into one fake project just because both mention SeedTalent.

## Non-negotiable boundary

This is not a backend integration, scraper, reverse-engineering project, or attempt to bypass SeedTalent access controls. It is an authorized screen/audio capture and content reconstruction pipeline.

Allowed patterns:

- human-guided browser capture
- headed browser automation that mimics approved user navigation
- screen recording
- audio recording
- screenshots
- OCR
- speech transcription
- keyframe extraction
- UI-visible report download handling
- metadata logging for URL, page title, timestamps, and operator notes

Disallowed patterns:

- backend API probing
- hidden endpoint extraction
- network interception
- credential sharing
- reverse engineering SeedTalent software
- bypassing access controls
- storing production credentials in code
- committing real SeedTalent content, employee PII, or customer data to the repo

## Architecture summary

```text
Authorized SeedTalent account
  -> controlled browser capture session
  -> screen/audio recording + screenshots + event metadata
  -> OCR + transcription + keyframes
  -> course/lesson reconstruction
  -> source-linked content chunks
  -> rights/PII/jurisdiction/human review
  -> approved RAG/search layer
  -> draft training generation
  -> human approval
  -> internal training library
```

## First local setup

This scaffold is intentionally lightweight. It gives Codex enough context to start building while avoiding real credentials or production data.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Recommended first Codex prompt: see `prompts/00_codex_bootstrap_prompt.md`.

## Canonical repo

Canonical local root:

`C:\dev\Learning Capture Pipeline`

Canonical GitHub repo:

`https://github.com/xylent-studio/learning_capture_pipeline`

Default branch:

`main`

This workspace stays at `C:\dev\Learning Capture Pipeline` so the local `_intel` continuity surfaces, restore anchors, and checkpoints remain valid.

## Public repo posture

The canonical GitHub repo is public by explicit choice. Treat that as a publishing constraint on every change.

Never commit:

- real permission manifests
- real credentials or secret material
- Playwright storage state
- raw capture artifacts
- imported context packs
- real SeedTalent content
- employee PII

Use only placeholder/example manifests in `config/`, keep runtime auth state under ignored local paths such as `.secrets/`, and keep raw capture outputs in ignored local artifact storage.

## Repo map

```text
AGENTS.md                         durable Codex/repo instructions
PLANS.md                          execution-plan template for long tasks
.codex/config.example.toml         example repo-specific Codex config
.agents/skills/*/SKILL.md          local Codex skills for repeatable work
docs/                              architecture, SOP, governance, data model, tooling
prompts/                           Codex bootstrap prompts and first tickets
src/som_seedtalent_capture/        starter Python package
tests/                             starter tests and fixture README
migrations/                        initial SQL schema draft
```

## Working method

Use one branch per bounded ticket. Each task should state:

- goal
- context
- constraints
- done-when criteria
- tests to run

Every generated or reconstructed training artifact starts as `needs_review`. No generated output is publishable by default.


## Contract-verified full-autonomy mode

State of Mind has represented that SeedTalent and relevant vendors have contractually authorized use of the covered content for this project, including capture and derivative internal training use. The system should therefore treat `seedtalent_contract_full_use` as the primary permission basis for in-scope courses and vendor materials.

The permissions layer is not meant to block authorized work. It exists to attach proof of permission, scope, vendor, course, and audit metadata to every capture and generated artifact. Rights flags should only be raised when a course or asset falls outside the permission manifest, when vendor scope is missing, when PII handling is uncertain, or when a capture includes pages outside the approved SeedTalent training scope.

The target operating model is fully autonomous capture: after credential/auth bootstrap, the bot discovers courses through the visible UI, creates a capture plan, starts screen/audio recording, navigates lessons, handles videos/static pages/quizzes/reports, creates QA reports, retries safe failures, and sends only exceptions to humans.

Recommended first Codex prompt for this mode: `prompts/03_codex_contract_verified_full_autonomy_prompt.md`.
