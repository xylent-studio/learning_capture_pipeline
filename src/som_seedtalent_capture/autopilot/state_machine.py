from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AutopilotState(StrEnum):
    INIT = "init"
    LOAD_PERMISSION_MANIFEST = "load_permission_manifest"
    AUTH_PREFLIGHT = "auth_preflight"
    DISCOVER_CATALOG = "discover_catalog"
    BUILD_COURSE_INVENTORY = "build_course_inventory"
    BUILD_CAPTURE_PLAN = "build_capture_plan"
    START_BROWSER = "start_browser"
    START_RECORDER = "start_recorder"
    OPEN_COURSE = "open_course"
    CAPTURE_OVERVIEW = "capture_overview"
    CAPTURE_LESSON_LIST = "capture_lesson_list"
    ENTER_LESSON = "enter_lesson"
    CLASSIFY_PAGE = "classify_page"
    CAPTURE_STATIC_PAGE = "capture_static_page"
    CAPTURE_VIDEO_PAGE = "capture_video_page"
    CAPTURE_AUDIO_PAGE = "capture_audio_page"
    CAPTURE_QUIZ_PAGE = "capture_quiz_page"
    CAPTURE_FEEDBACK_PAGE = "capture_feedback_page"
    ADVANCE_LESSON = "advance_lesson"
    CAPTURE_COMPLETION = "capture_completion"
    STOP_RECORDER = "stop_recorder"
    RUN_PROCESSING = "run_processing"
    GENERATE_QA = "generate_qa"
    QUEUE_RECONSTRUCTION = "queue_reconstruction"
    QUEUE_RECAPTURE = "queue_recapture"
    ESCALATE_HUMAN = "escalate_human"
    DONE = "done"


class PageKind(StrEnum):
    AUTH_REQUIRED = "auth_required"
    DASHBOARD = "dashboard"
    CATALOG = "catalog"
    ASSIGNED_LEARNING = "assigned_learning"
    COURSE_CARD = "course_card"
    COURSE_OVERVIEW = "course_overview"
    LESSON_LIST = "lesson_list"
    LESSON_STATIC_TEXT = "lesson_static_text"
    LESSON_VIDEO = "lesson_video"
    LESSON_AUDIO = "lesson_audio"
    LESSON_SLIDES = "lesson_slides"
    QUIZ_QUESTION = "quiz_question"
    QUIZ_FEEDBACK = "quiz_feedback"
    COMPLETION_PAGE = "completion_page"
    CERTIFICATE_PAGE = "certificate_page"
    REPORT_TABLE = "report_table"
    REPORT_EXPORT = "report_export"
    UNKNOWN = "unknown"


class NavigationAction(StrEnum):
    REAUTH_OR_STOP = "reauth_or_stop"
    COLLECT_COURSE_CARDS = "collect_course_cards"
    CAPTURE_OVERVIEW_AND_START = "capture_overview_and_start"
    COLLECT_LESSONS_AND_ENTER_NEXT = "collect_lessons_and_enter_next"
    CAPTURE_STATIC_SCROLL_AND_NEXT = "capture_static_scroll_and_next"
    PLAY_MEDIA_WAIT_AND_NEXT = "play_media_wait_and_next"
    CAPTURE_QUIZ_APPLY_POLICY = "capture_quiz_apply_policy"
    CAPTURE_FEEDBACK_AND_NEXT = "capture_feedback_and_next"
    CAPTURE_COMPLETION_AND_STOP = "capture_completion_and_stop"
    CAPTURE_REPORT = "capture_report"
    RETRY_OR_ESCALATE = "retry_or_escalate"


class MediaSummary(BaseModel):
    count: int = 0
    duration_seconds: float | None = None
    current_time_seconds: float | None = None
    paused: bool | None = None


class PageObservation(BaseModel):
    url: str
    title: str | None = None
    page_kind: PageKind = PageKind.UNKNOWN
    visible_text_sample: str | None = None
    buttons: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    media: MediaSummary = Field(default_factory=MediaSummary)
    screenshot_uri: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class CaptureDecision(BaseModel):
    action: NavigationAction
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human: bool = False


def decide_next_action(observation: PageObservation) -> CaptureDecision:
    mapping = {
        PageKind.AUTH_REQUIRED: (NavigationAction.REAUTH_OR_STOP, "auth_required", True),
        PageKind.CATALOG: (NavigationAction.COLLECT_COURSE_CARDS, "catalog_visible", False),
        PageKind.ASSIGNED_LEARNING: (NavigationAction.COLLECT_COURSE_CARDS, "assigned_learning_visible", False),
        PageKind.COURSE_OVERVIEW: (NavigationAction.CAPTURE_OVERVIEW_AND_START, "course_overview_visible", False),
        PageKind.LESSON_LIST: (NavigationAction.COLLECT_LESSONS_AND_ENTER_NEXT, "lesson_list_visible", False),
        PageKind.LESSON_STATIC_TEXT: (NavigationAction.CAPTURE_STATIC_SCROLL_AND_NEXT, "static_lesson_visible", False),
        PageKind.LESSON_VIDEO: (NavigationAction.PLAY_MEDIA_WAIT_AND_NEXT, "video_lesson_visible", False),
        PageKind.LESSON_AUDIO: (NavigationAction.PLAY_MEDIA_WAIT_AND_NEXT, "audio_lesson_visible", False),
        PageKind.QUIZ_QUESTION: (NavigationAction.CAPTURE_QUIZ_APPLY_POLICY, "quiz_question_visible", False),
        PageKind.QUIZ_FEEDBACK: (NavigationAction.CAPTURE_FEEDBACK_AND_NEXT, "quiz_feedback_visible", False),
        PageKind.COMPLETION_PAGE: (NavigationAction.CAPTURE_COMPLETION_AND_STOP, "completion_visible", False),
        PageKind.CERTIFICATE_PAGE: (NavigationAction.CAPTURE_COMPLETION_AND_STOP, "certificate_visible", False),
        PageKind.REPORT_TABLE: (NavigationAction.CAPTURE_REPORT, "report_table_visible", False),
        PageKind.REPORT_EXPORT: (NavigationAction.CAPTURE_REPORT, "report_export_visible", False),
    }
    action, reason, human = mapping.get(
        observation.page_kind,
        (NavigationAction.RETRY_OR_ESCALATE, "unknown_page_kind", True),
    )
    return CaptureDecision(
        action=action,
        reason=reason,
        confidence=max(observation.confidence, 0.5 if not human else 0.2),
        requires_human=human,
    )
