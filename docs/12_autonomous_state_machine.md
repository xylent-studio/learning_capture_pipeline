# 12 Autonomous State Machine

## Purpose

The autonomous runner should be implemented as a state machine, not a loose script. SeedTalent course players may vary by vendor, lesson type, media player, quiz, and completion state. A state machine makes retries, QA, and exception handling explicit.

## Top-level states

```text
INIT
LOAD_PERMISSION_MANIFEST
AUTH_PREFLIGHT
DISCOVER_CATALOG
BUILD_COURSE_INVENTORY
BUILD_CAPTURE_PLAN
START_BROWSER
START_RECORDER
OPEN_COURSE
CAPTURE_OVERVIEW
CAPTURE_LESSON_LIST
ENTER_LESSON
CLASSIFY_PAGE
CAPTURE_STATIC_PAGE
CAPTURE_VIDEO_PAGE
CAPTURE_AUDIO_PAGE
CAPTURE_SLIDES_PAGE
CAPTURE_QUIZ_PAGE
CAPTURE_FEEDBACK_PAGE
ADVANCE_LESSON
CAPTURE_COMPLETION
STOP_RECORDER
RUN_PROCESSING
GENERATE_QA
DECIDE_PASS_FAIL
QUEUE_RECONSTRUCTION
QUEUE_RECAPTURE
ESCALATE_HUMAN
DONE
```

## Observations

At each step the runner should produce a `PageObservation`:

```json
{
  "url": "...",
  "title": "...",
  "page_kind": "lesson_video",
  "visible_text_sample": "...",
  "buttons": ["Start", "Next", "Submit"],
  "links": ["Course Catalog"],
  "media_elements": [{"duration": 340, "current_time": 12, "paused": false}],
  "screenshot_uri": "s3://...",
  "confidence": 0.88
}
```

## Decisions

The state machine converts observations into actions:

```text
auth_required        -> reauth_or_stop
catalog              -> collect_course_cards
course_overview      -> screenshot_scroll_extract_and_start
lesson_list          -> collect_lessons_and_enter_next
lesson_static_text   -> full_page_screenshot_dom_extract_scroll_then_next
lesson_video         -> play_video_wait_to_end_capture_then_next
lesson_audio         -> play_audio_wait_to_end_capture_then_next
quiz_question        -> capture_question_apply_quiz_policy_submit
quiz_feedback        -> capture_feedback_then_next
completion_page      -> capture_completion_stop_recorder
unknown              -> screenshot_dom_extract_retry_or_escalate
```

## Watchdogs

Every state needs watchdogs:

- max time in state,
- max click retries,
- max unchanged-screen interval,
- audio/video progress detection,
- navigation timeout,
- unexpected logout detection,
- safe stop on prohibited page,
- safe stop on repeated unknown state.

## QA events

The runner should emit QA-relevant events while navigating:

- lesson_started
- lesson_completed
- media_play_started
- media_play_completed
- static_page_captured
- quiz_question_captured
- quiz_feedback_captured
- report_export_downloaded
- unexpected_auth_required
- prohibited_path_detected
- unknown_ui_state
- recapture_reason_added
