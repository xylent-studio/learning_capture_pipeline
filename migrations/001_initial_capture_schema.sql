-- Initial schema draft for State of Mind SeedTalent authorized capture pipeline.
-- This is a starting point. Convert to Alembic once the database layer is implemented.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS capture_batch (
    capture_batch_id TEXT PRIMARY KEY,
    permission_basis TEXT NOT NULL DEFAULT 'seedtalent_contract_full_use',
    scope_description TEXT NOT NULL,
    operator TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS capture_session (
    capture_session_id TEXT PRIMARY KEY,
    capture_batch_id TEXT NOT NULL REFERENCES capture_batch(capture_batch_id),
    source_platform TEXT NOT NULL DEFAULT 'seedtalent',
    capture_mode TEXT NOT NULL DEFAULT 'authorized_screen_capture',
    source_url TEXT,
    course_title TEXT,
    module_title TEXT,
    lesson_title TEXT,
    brand TEXT,
    jurisdiction TEXT,
    raw_video_uri TEXT,
    raw_audio_uri TEXT,
    screenshot_folder_uri TEXT,
    browser_profile TEXT,
    viewport_width INTEGER NOT NULL DEFAULT 1920,
    viewport_height INTEGER NOT NULL DEFAULT 1080,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    qa_status TEXT NOT NULL DEFAULT 'needs_review',
    permission_basis TEXT NOT NULL DEFAULT 'seedtalent_contract_full_use',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS capture_event (
    event_id TEXT PRIMARY KEY,
    capture_session_id TEXT NOT NULL REFERENCES capture_session(capture_session_id),
    event_type TEXT NOT NULL,
    timestamp_ms BIGINT NOT NULL CHECK (timestamp_ms >= 0),
    url TEXT,
    page_title TEXT,
    visible_label TEXT,
    operator_note TEXT,
    screenshot_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS visual_frame (
    frame_id TEXT PRIMARY KEY,
    capture_session_id TEXT NOT NULL REFERENCES capture_session(capture_session_id),
    timestamp_ms BIGINT NOT NULL CHECK (timestamp_ms >= 0),
    image_uri TEXT NOT NULL,
    ocr_text TEXT,
    ocr_confidence NUMERIC CHECK (ocr_confidence >= 0 AND ocr_confidence <= 1),
    detected_entities JSONB NOT NULL DEFAULT '[]'::jsonb,
    slide_change_score NUMERIC CHECK (slide_change_score >= 0 AND slide_change_score <= 1),
    review_status TEXT NOT NULL DEFAULT 'needs_review'
);

CREATE TABLE IF NOT EXISTS audio_transcript_segment (
    segment_id TEXT PRIMARY KEY,
    capture_session_id TEXT NOT NULL REFERENCES capture_session(capture_session_id),
    start_ms BIGINT NOT NULL CHECK (start_ms >= 0),
    end_ms BIGINT NOT NULL CHECK (end_ms > start_ms),
    speaker TEXT,
    text TEXT NOT NULL,
    confidence NUMERIC CHECK (confidence >= 0 AND confidence <= 1),
    review_status TEXT NOT NULL DEFAULT 'needs_review'
);

CREATE TABLE IF NOT EXISTS reconstructed_lesson (
    lesson_id TEXT PRIMARY KEY,
    capture_session_id TEXT NOT NULL REFERENCES capture_session(capture_session_id),
    course_title TEXT,
    module_title TEXT,
    lesson_title TEXT NOT NULL,
    lesson_order INTEGER CHECK (lesson_order >= 0),
    summary TEXT,
    learning_objectives JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_start_ms BIGINT NOT NULL CHECK (source_start_ms >= 0),
    source_end_ms BIGINT NOT NULL CHECK (source_end_ms > source_start_ms),
    review_status TEXT NOT NULL DEFAULT 'needs_review'
);

CREATE TABLE IF NOT EXISTS content_chunk (
    chunk_id TEXT PRIMARY KEY,
    capture_session_id TEXT NOT NULL REFERENCES capture_session(capture_session_id),
    lesson_id TEXT REFERENCES reconstructed_lesson(lesson_id),
    chunk_type TEXT NOT NULL,
    text TEXT NOT NULL,
    source_start_ms BIGINT CHECK (source_start_ms >= 0),
    source_end_ms BIGINT CHECK (source_end_ms IS NULL OR source_start_ms IS NULL OR source_end_ms > source_start_ms),
    source_screenshot_uri TEXT,
    source_video_uri TEXT,
    brand TEXT,
    jurisdiction TEXT,
    rights_status TEXT NOT NULL DEFAULT 'unknown',
    pii_status TEXT NOT NULL DEFAULT 'none_detected',
    review_status TEXT NOT NULL DEFAULT 'needs_review',
    embedding_id TEXT,
    embedding vector(1536),
    CHECK (source_start_ms IS NOT NULL OR source_end_ms IS NOT NULL OR source_screenshot_uri IS NOT NULL OR source_video_uri IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS capture_qa_report (
    qa_report_id TEXT PRIMARY KEY,
    capture_session_id TEXT NOT NULL REFERENCES capture_session(capture_session_id),
    generated_at TIMESTAMPTZ NOT NULL,
    duration_ms BIGINT CHECK (duration_ms >= 0),
    audio_detected BOOLEAN,
    screenshot_count INTEGER NOT NULL DEFAULT 0 CHECK (screenshot_count >= 0),
    transcript_segment_count INTEGER NOT NULL DEFAULT 0 CHECK (transcript_segment_count >= 0),
    visual_frame_count INTEGER NOT NULL DEFAULT 0 CHECK (visual_frame_count >= 0),
    low_confidence_transcript_count INTEGER NOT NULL DEFAULT 0 CHECK (low_confidence_transcript_count >= 0),
    low_confidence_ocr_count INTEGER NOT NULL DEFAULT 0 CHECK (low_confidence_ocr_count >= 0),
    possible_pii_count INTEGER NOT NULL DEFAULT 0 CHECK (possible_pii_count >= 0),
    missing_sections JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommended_status TEXT NOT NULL DEFAULT 'needs_review',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS review_decision (
    review_decision_id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_training_module (
    module_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    target_role TEXT,
    topic TEXT NOT NULL,
    jurisdiction TEXT,
    format TEXT NOT NULL,
    body_json JSONB NOT NULL,
    source_chunk_ids JSONB NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'needs_review',
    created_at TIMESTAMPTZ NOT NULL,
    approved_by TEXT,
    approved_at TIMESTAMPTZ
);
