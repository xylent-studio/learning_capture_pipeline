from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright
from pydantic import BaseModel, Field

from som_seedtalent_capture import __version__
from som_seedtalent_capture.autopilot.capture_plan import CapturePlan, QaThresholds, QuizCaptureMode, RecorderProfile
from som_seedtalent_capture.autopilot.course_discovery import CourseDiscoveryResult, CourseInventoryItem
from som_seedtalent_capture.autopilot.state_machine import PageKind, PageObservation
from som_seedtalent_capture.auth import AuthPreflightStatus, PlaywrightVisibleAuthPreflight, run_auth_preflight
from som_seedtalent_capture.config import PilotCourseSelection, RuntimePilotConfig
from som_seedtalent_capture.permissions import PermissionManifest, authorize_capture


class AuthBootstrapPreparation(BaseModel):
    account_alias: str
    secret_root: str
    permission_manifest_path: str
    storage_state_path: str
    auth_screenshot_dir: str
    artifact_root: str
    approved_courses_path: str
    created_directories: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)


class PilotBatchMetadata(BaseModel):
    batch_id: str
    account_alias: str
    runner_version: str
    artifact_root: str
    selected_course_count: int = Field(ge=0)
    readiness_status: str
    recapture_status: str


class PilotPlanBundle(BaseModel):
    metadata: PilotBatchMetadata
    plans: list[CapturePlan] = Field(default_factory=list)


def prepare_auth_bootstrap(config: RuntimePilotConfig) -> AuthBootstrapPreparation:
    created_directories: list[str] = []
    directories = [
        config.external_paths.secret_root,
        config.external_paths.permission_manifest_path.parent,
        config.external_paths.storage_state_path.parent,
        config.external_paths.auth_screenshot_dir,
        config.external_paths.artifact_root,
        config.external_paths.approved_courses_path.parent,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        created_directories.append(str(directory))
    return AuthBootstrapPreparation(
        account_alias=config.account_alias,
        secret_root=str(config.external_paths.secret_root),
        permission_manifest_path=str(config.external_paths.permission_manifest_path),
        storage_state_path=str(config.external_paths.storage_state_path),
        auth_screenshot_dir=str(config.external_paths.auth_screenshot_dir),
        artifact_root=str(config.external_paths.artifact_root),
        approved_courses_path=str(config.external_paths.approved_courses_path),
        created_directories=created_directories,
        recommended_commands=[
            "som-capture pilot validate-config --config <runtime-config.yaml>",
            "som-capture pilot bootstrap-auth --config <runtime-config.yaml>",
            "som-capture pilot auth-preflight --config <runtime-config.yaml> --headed",
            "som-capture pilot discovery --config <runtime-config.yaml> --headed",
            "som-capture pilot plans-from-approved --config <runtime-config.yaml>",
        ],
    )


def _extract_visible_course_cards(page: Page) -> list[dict[str, str | None]]:
    cards = []
    card_locator = page.locator("section.course-card, article.course-card, [data-course-card]")
    for index in range(card_locator.count()):
        card = card_locator.nth(index)
        link = card.locator("a").first
        heading = card.locator("h1, h2, h3").first
        vendor_text = next(
            (text for text in card.locator("p").all_inner_texts() if text.lower().startswith("vendor:")),
            None,
        )
        paragraphs = [text.strip() for text in card.locator("p").all_inner_texts() if text.strip()]
        summary = next((text for text in paragraphs if not text.lower().startswith("vendor:") and "assigned course" not in text.lower()), None)
        course_title = heading.inner_text().strip() if heading.count() else None
        href = link.get_attribute("href") if link.count() else None
        cards.append(
            {
                "course_title": course_title,
                "vendor": vendor_text.split(":", maxsplit=1)[1].strip() if vendor_text else None,
                "summary": summary,
                "href": href,
            }
        )
    return cards


def run_visible_catalog_discovery(
    *,
    config: RuntimePilotConfig,
    manifest: PermissionManifest,
    headless: bool = True,
) -> CourseDiscoveryResult:
    config.external_paths.auth_screenshot_dir.mkdir(parents=True, exist_ok=True)
    preflight = PlaywrightVisibleAuthPreflight(
        screenshot_dir=config.external_paths.auth_screenshot_dir,
        authenticated_indicators=config.tuning.authenticated_indicators,
        auth_expired_indicators=config.tuning.auth_expired_indicators,
        prohibited_path_patterns=config.tuning.prohibited_path_patterns,
        headless=headless,
    )
    preflight_result = run_auth_preflight(
        mode=config.auth_mode,
        storage_state_path=config.external_paths.storage_state_path,
        base_url=config.seedtalent_base_url,
        browser_preflight=preflight,
        repo_root=Path.cwd(),
        account_alias=config.account_alias,
        allowed_storage_root=config.external_paths.secret_root,
    )
    if preflight_result.status != AuthPreflightStatus.AUTHENTICATED:
        raise ValueError(f"catalog discovery requires authenticated preflight, got {preflight_result.status.value}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(config.external_paths.storage_state_path))
        page = context.new_page()
        page.goto(config.seedtalent_base_url, wait_until="domcontentloaded")
        current_url = page.url
        screenshot_uri = str((config.external_paths.auth_screenshot_dir / "catalog-discovery.png").resolve())
        page.screenshot(path=screenshot_uri, full_page=True)
        cards = _extract_visible_course_cards(page)
        observation = PageObservation(
            url=current_url,
            title=page.title(),
            page_kind=PageKind.CATALOG,
            visible_text_sample=page.locator("body").inner_text()[:300],
            buttons=[text.strip() for text in page.locator("button:visible").all_inner_texts() if text.strip()],
            links=[text.strip() for text in page.locator("a:visible").all_inner_texts() if text.strip()],
            screenshot_uri=screenshot_uri,
            confidence=0.75,
        )
        browser.close()

    items = []
    for card in cards:
        items.append(
            CourseInventoryItem(
                course_title=card["course_title"] or "Unknown course",
                vendor=card["vendor"],
                source_url=urljoin(current_url, card["href"] or ""),
                catalog_url=current_url,
                screenshot_uri=screenshot_uri,
                summary=card["summary"],
                discovery_page_kind=PageKind.CATALOG,
                authorization=authorize_capture(
                    url=urljoin(current_url, card["href"] or ""),
                    vendor=card["vendor"],
                    course_title=card["course_title"],
                    manifest=manifest,
                ),
            )
        )

    return CourseDiscoveryResult(
        catalog_url=current_url,
        screenshot_uri=screenshot_uri,
        observation=observation,
        items=items,
    )


def build_pilot_plan_bundle(
    *,
    selection: PilotCourseSelection,
    config: RuntimePilotConfig,
    plans: list[CapturePlan],
) -> PilotPlanBundle:
    return PilotPlanBundle(
        metadata=PilotBatchMetadata(
            batch_id=f"pilot-{config.account_alias}",
            account_alias=selection.account_alias or config.account_alias,
            runner_version=__version__,
            artifact_root=str(config.external_paths.artifact_root),
            selected_course_count=len(selection.courses),
            readiness_status="ready_for_live_auth",
            recapture_status="none",
        ),
        plans=plans,
    )


def build_capture_plans_from_selection(
    *,
    selection: PilotCourseSelection,
    config: RuntimePilotConfig,
    manifest: PermissionManifest,
) -> list[CapturePlan]:
    plans: list[CapturePlan] = []
    for course in selection.courses:
        authorization = authorize_capture(
            url=course.source_url,
            vendor=course.vendor,
            course_title=course.course_title,
            manifest=manifest,
        )
        if not authorization.authorized:
            raise ValueError(f"Approved course input is not authorized: {course.course_title}")

        plans.append(
            CapturePlan(
                course_title=course.course_title,
                source_url=course.source_url,
                permission_basis=authorization.permission_basis,
                rights_status=authorization.rights_status,
                screenshot_interval_seconds=config.tuning.screenshot_interval_seconds,
                recorder_profile=RecorderProfile.HEADED_BROWSER_FFMPEG,
                quiz_mode=QuizCaptureMode.CAPTURE_AND_COMPLETE_ON_CAPTURE_ACCOUNT,
                max_course_duration_minutes=course.estimated_duration_minutes or 60,
                expected_lesson_count=None,
                lesson_list_url=None,
                lesson_urls=[],
                lesson_list_observation=None,
                qa_thresholds=QaThresholds(
                    min_page_observations=1,
                    min_screenshot_count=1,
                    min_classifier_confidence=0.7,
                    require_quiz_capture=True,
                    require_completion_capture=True,
                ),
            )
        )
    return plans
