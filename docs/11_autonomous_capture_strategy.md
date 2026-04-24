# 11 Autonomous Capture Strategy

## Objective

The target is a fully autonomous SeedTalent capture bot. Manual capture is only a calibration, fallback, or exception path.

The autonomous bot should discover authorized courses through the visible SeedTalent UI, create a capture plan, start recording, navigate lessons, capture video/audio/screenshots/visible DOM text, process quizzes and reports, generate a QA report, retry safe failures, and queue only exceptions for humans.

## Permission assumption

State of Mind has represented that SeedTalent and relevant vendors have contractually authorized the covered content for capture and derivative internal training use. Therefore, in-scope content should default to:

```text
permission_basis = seedtalent_contract_full_use
rights_status = seedtalent_contract_full_use
ai_use_allowed = true
derivative_use_allowed = true
```

The system should not treat generic rights uncertainty as a blocker for in-scope content. It should flag only out-of-scope content, missing manifest coverage, PII issues, or prohibited capture mechanisms.

## Autonomy levels

### A0: Manual capture

An operator drives the browser. The system records screen/audio, screenshots, notes, and QA metadata.

### A1: Assisted capture

The bot launches the browser, starts recording, maintains timestamps, takes screenshots, and collects metadata. The operator still clicks through the course.

### A2: Scripted autonomous capture

The bot follows a known course-player flow using stable selectors, visible labels, role locators, scroll behavior, media controls, and completion checks.

### A3: Self-discovering autonomous capture

The bot discovers course links from catalog/assigned-learning pages, infers lesson lists, classifies screens, and chooses the correct action without pre-authored course scripts.

### A4: Scheduled autonomous capture fleet

The bot runs capture batches from a queue, refreshes auth safely, captures courses overnight, generates QA reports, retries failures, and escalates only exceptions.

The MVP should aim directly for A2 on a fake local SeedTalent-like fixture, then A2 on real SeedTalent, then A3/A4.

## Core autonomous loop

```text
load permission manifest
  -> auth preflight
  -> scope preflight
  -> catalog discovery
  -> course inventory
  -> course capture plan
  -> launch headed browser
  -> start recorder
  -> navigate course
  -> capture visible DOM + screenshots + video/audio + events
  -> detect lesson/page/video/quiz/completion states
  -> stop recorder
  -> process transcript/OCR/keyframes
  -> generate QA report
  -> pass/fail coverage gates
  -> enqueue reconstruction or recapture
```

## Capture mechanisms

Use all approved user-visible capture channels:

- Screen recording.
- System/browser audio recording.
- Browser screenshots.
- Full-page screenshots when available.
- Visible DOM text extraction.
- Visible UI table extraction.
- Download buttons exposed in the UI.
- OCR for screenshots/keyframes.
- Speech-to-text for audio/video.

Visible DOM extraction is acceptable in this design because it reads text that the authorized browser session can see. It is not hidden API access, network interception, or backend probing.

## Authentication model

Preferred sequence:

1. Dedicated SeedTalent capture account.
2. Manual login once through a normal browser.
3. Persist browser storage state outside the repo.
4. Bot reuses storage state for capture sessions.
5. If the session expires, bot either triggers manual reauth or uses an approved vault-backed login flow.

Do not store credentials in source code, prompt files, fixtures, screenshots, logs, or artifact metadata.

## Navigation strategy

Priority order:

1. Playwright locators by role, label, visible text, and semantic structure.
2. Course-player rules for known SeedTalent screens.
3. Visible DOM text/classification.
4. OCR/vision detection on screenshots.
5. Coordinate clicks only as a last resort within visible authorized UI.
6. Human escalation if confidence is low.

## Page classifications

Every observed page/player state should be classified as one of:

- auth_required
- dashboard
- catalog
- assigned_learning
- course_card
- course_overview
- lesson_list
- lesson_static_text
- lesson_video
- lesson_audio
- lesson_slides
- quiz_question
- quiz_feedback
- completion_page
- certificate_page
- report_table
- report_export
- unknown

## Success criteria

A capture is successful only when:

- raw recording exists,
- audio was captured when expected,
- screenshots were captured,
- visible DOM/OCR/transcript data exists,
- course start and finish were captured,
- expected lessons were covered or exception is documented,
- quizzes/reports were handled according to policy,
- no prohibited pages were captured,
- QA status is ready_for_reconstruction.
