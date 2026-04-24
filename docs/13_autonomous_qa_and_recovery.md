# 13 Autonomous QA and Recovery

## QA philosophy

Autonomous capture should not merely trust that the browser reached a completion screen. It should prove the capture is usable.

## Required QA signals

- recording file exists and has non-trivial duration,
- audio level is above threshold where media was expected,
- screenshot count is above threshold,
- visible DOM text was captured where available,
- OCR text exists for screenshot-only content,
- transcript exists for media content,
- lesson count matches expected count or an exception is recorded,
- static pages were scrolled sufficiently,
- videos reached end or Next became enabled,
- quizzes were captured according to policy,
- completion/certificate page was captured when present,
- no excluded paths were captured,
- PII was separated from training content.

## Recapture reasons

- auth_expired
- prohibited_path_detected
- navigation_timeout
- missing_audio
- media_not_playing
- video_progress_stalled
- low_ocr_confidence
- low_transcript_confidence
- unexpected_quiz_blocker
- completion_not_detected
- lesson_count_mismatch
- possible_pii
- unknown_ui_state
- recorder_failure
- screenshot_failure

## Recovery strategy

Safe retries:

- reload page once,
- reopen course from inventory,
- retry click using alternate locator,
- scroll and reclassify,
- restart recorder before content begins,
- re-run static page capture,
- re-run video if video did not progress.

Unsafe retries:

- repeated login attempts,
- actions on billing/settings/account/private-message pages,
- endless quiz guessing,
- repeated clicks on unknown UI elements,
- bypass attempts.

Unsafe retries should stop and create a human exception.

## Confidence score

Each session should get an aggregate score:

```text
coverage_score
audio_score
visual_score
transcript_score
ocr_score
navigation_score
scope_score
pii_score
```

Only sessions above threshold move to reconstruction automatically.
