# Data model

## capture_batch

Represents a group of related capture sessions.

Fields:

- capture_batch_id
- permission_basis
- scope_description
- operator
- started_at
- completed_at
- status
- notes

## capture_session

Represents a single browser/screen recording session.

Fields:

- capture_session_id
- capture_batch_id
- source_platform
- source_url
- course_title
- module_title
- lesson_title
- brand
- jurisdiction
- raw_video_uri
- raw_audio_uri
- screenshot_folder_uri
- browser_profile
- viewport_width
- viewport_height
- started_at
- ended_at
- status
- qa_status
- notes

## capture_event

Represents click, page load, scroll, screenshot, note, or media events.

Fields:

- event_id
- capture_session_id
- event_type
- timestamp_ms
- url
- page_title
- visible_label
- operator_note
- screenshot_uri

## visual_frame

Represents screenshots/keyframes and OCR outputs.

Fields:

- frame_id
- capture_session_id
- timestamp_ms
- image_uri
- ocr_text
- ocr_confidence
- detected_entities
- slide_change_score
- review_status

## audio_transcript_segment

Represents timestamped transcript segments.

Fields:

- segment_id
- capture_session_id
- start_ms
- end_ms
- speaker
- text
- confidence
- review_status

## reconstructed_lesson

Represents a lesson inferred from capture events, OCR, transcript, and notes.

Fields:

- lesson_id
- capture_session_id
- course_title
- module_title
- lesson_title
- lesson_order
- summary
- learning_objectives
- source_start_ms
- source_end_ms
- review_status

## content_chunk

Represents searchable/retrievable chunks.

Fields:

- chunk_id
- lesson_id
- capture_session_id
- chunk_type
- text
- source_start_ms
- source_end_ms
- source_screenshot_uri
- source_video_uri
- brand
- jurisdiction
- rights_status
- pii_status
- review_status
- embedding_id

## generated_training_module

Represents draft training outputs.

Fields:

- module_id
- title
- target_role
- topic
- jurisdiction
- format
- body_json
- source_chunk_ids
- review_status
- created_by
- approved_by
- approved_at

## learner analytics separation

Report/completion/certification data should live in separate tables and should not be mixed with training content chunks unless heavily aggregated and reviewed.
