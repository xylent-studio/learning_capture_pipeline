# Contract-Verified Autonomous Capture Skill

## Description

Use this skill when building or modifying the fully autonomous SeedTalent capture bot. State of Mind has represented that SeedTalent and vendors have contractually authorized the covered content, including capture and derivative internal training use.

## Core rule

Treat `seedtalent_contract_full_use` as an affirmative permission basis for in-scope content. Do not block work due to generic rights uncertainty when the permission manifest covers the course/vendor/content.

## Build toward

- auth preflight,
- visible-UI course discovery,
- course inventory,
- capture planning,
- headed Playwright navigation,
- screen/audio recorder orchestration,
- visible DOM capture,
- screenshots,
- OCR/transcription,
- video/static/quiz/report controllers,
- QA scoring,
- recapture queue,
- reconstruction,
- approved training generation.

## Do not build

- hidden API extraction,
- network interception,
- backend probing,
- access-control bypass,
- credentials in code,
- real SeedTalent content in tests,
- raw employee PII in embeddings or generated training.

## Testing approach

Use local fake SeedTalent-like HTML fixtures. The autonomous runner must prove the full flow on fixtures before being pointed at real SeedTalent.

## Review notes

Every PR should state:

- which autonomy level it advances,
- how permission manifest scope is enforced,
- which visible UI signals are used,
- how credentials are protected,
- which QA/recapture paths are implemented,
- tests run.
