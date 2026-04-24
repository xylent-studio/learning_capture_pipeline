from pathlib import Path

import pytest

from som_seedtalent_capture.auth import AuthMode, AuthPreflightResult, AuthPreflightStatus
from som_seedtalent_capture.config import ExternalPathConfig, PilotCourseSelection, PilotCourseSelectionItem, RuntimePilotConfig, SelectorTuningConfig
from som_seedtalent_capture.permissions import PermissionManifest
from som_seedtalent_capture.pilot_manifests import PilotBatchStatus, PilotRunStatus
from som_seedtalent_capture.pilot_runtime import (
    build_capture_plans_from_selection,
    build_pilot_plan_bundle,
    load_pilot_plan_bundle,
    prepare_auth_bootstrap,
    run_pilot_batch_skeleton,
    run_pilot_course_skeleton,
    run_visible_catalog_discovery,
)


def _config(tmp_path: Path) -> RuntimePilotConfig:
    secret_root = tmp_path / "secrets"
    artifact_root = tmp_path / "artifacts"
    storage_state_path = secret_root / "playwright" / "storage-state.json"
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    storage_state_path.write_text('{"cookies": []}', encoding="utf-8")
    return RuntimePilotConfig(
        seedtalent_base_url="https://app.seedtalent.com/catalog",
        account_alias="seedtalent-capture-bot",
        auth_mode=AuthMode.MANUAL_STORAGE_STATE,
        external_paths=ExternalPathConfig(
            secret_root=secret_root,
            permission_manifest_path=secret_root / "manifests" / "permission_manifest.yaml",
            storage_state_path=storage_state_path,
            auth_screenshot_dir=artifact_root / "preflight",
            artifact_root=artifact_root,
            approved_courses_path=secret_root / "inputs" / "approved_courses.yaml",
        ),
        tuning=SelectorTuningConfig(),
    )


def _manifest() -> PermissionManifest:
    return PermissionManifest(
        permission_manifest_id="pilot-runtime",
        contract_reference="pilot-runtime-contract",
        source_base_url="https://app.seedtalent.com",
        allowed_course_patterns=["*"],
    )


def test_prepare_auth_bootstrap_creates_expected_directories(tmp_path: Path):
    config = _config(tmp_path)

    preparation = prepare_auth_bootstrap(config)

    assert Path(preparation.secret_root).exists()
    assert Path(preparation.auth_screenshot_dir).exists()
    assert Path(preparation.artifact_root).exists()
    assert any("auth-preflight" in command or "bootstrap-auth" in command for command in preparation.recommended_commands)


def test_build_capture_plans_and_bundle_from_selection(tmp_path: Path):
    config = _config(tmp_path)
    selection = PilotCourseSelection(
        courses=[
            PilotCourseSelectionItem(
                course_title="Pilot Course",
                source_url="https://app.seedtalent.com/courses/pilot-course",
                vendor="Vendor A",
                estimated_duration_minutes=35,
            )
        ]
    )

    plans = build_capture_plans_from_selection(selection=selection, config=config, manifest=_manifest())
    bundle = build_pilot_plan_bundle(selection=selection, config=config, plans=plans)

    assert len(plans) == 1
    assert plans[0].recorder_profile.value == "headed_browser_ffmpeg"
    assert bundle.metadata.selected_course_count == 1
    assert bundle.metadata.account_alias == "seedtalent-capture-bot"


def test_load_pilot_plan_bundle_round_trips(tmp_path: Path):
    config = _config(tmp_path)
    selection = PilotCourseSelection(
        courses=[
            PilotCourseSelectionItem(
                course_title="Pilot Course",
                source_url="https://app.seedtalent.com/courses/pilot-course",
            )
        ]
    )
    bundle = build_pilot_plan_bundle(
        selection=selection,
        config=config,
        plans=build_capture_plans_from_selection(selection=selection, config=config, manifest=_manifest()),
    )
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")

    loaded = load_pilot_plan_bundle(bundle_path)

    assert loaded.metadata.batch_id == bundle.metadata.batch_id
    assert loaded.plans[0].course_title == "Pilot Course"


class _FakeStaticLocator:
    def __init__(self, texts: list[str] | None = None, text: str = "") -> None:
        self._texts = texts or []
        self._text = text

    def all_inner_texts(self) -> list[str]:
        return self._texts

    def inner_text(self) -> str:
        return self._text


class _FakePage:
    def __init__(self, screenshot_dir: Path) -> None:
        self.url = "https://app.seedtalent.com/catalog"
        self._screenshot_dir = screenshot_dir

    def goto(self, url: str, wait_until: str | None = None) -> None:
        del wait_until
        self.url = url

    def screenshot(self, path: str, full_page: bool = True) -> None:
        del full_page
        Path(path).write_text("fake screenshot", encoding="utf-8")

    def title(self) -> str:
        return "Catalog"

    def locator(self, selector: str):
        mapping = {
            "body": _FakeStaticLocator(text="Assigned Learning Catalog"),
            "button:visible": _FakeStaticLocator(texts=["Open Course"]),
            "a:visible": _FakeStaticLocator(texts=["Pilot Course"]),
        }
        return mapping[selector]


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def new_page(self) -> _FakePage:
        return self._page


class _FakeBrowser:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def new_context(self, storage_state: str):
        assert storage_state.endswith("storage-state.json")
        return _FakeContext(self._page)

    def close(self) -> None:
        return None


class _FakeChromium:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def launch(self, headless: bool = True):
        assert headless is True
        return _FakeBrowser(self._page)


class _FakePlaywrightContext:
    def __init__(self, page: _FakePage) -> None:
        self.chromium = _FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_run_visible_catalog_discovery_returns_authorized_items(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    config.external_paths.auth_screenshot_dir.mkdir(parents=True, exist_ok=True)
    fake_page = _FakePage(config.external_paths.auth_screenshot_dir)

    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTHENTICATED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            account_alias=kwargs["account_alias"],
            current_url="https://app.seedtalent.com/catalog",
        ),
    )
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.sync_playwright",
        lambda: _FakePlaywrightContext(fake_page),
    )
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime._extract_visible_course_cards",
        lambda page: [
            {
                "course_title": "Pilot Course",
                "vendor": "Vendor A",
                "summary": "Approved pilot course",
                "href": "/courses/pilot-course",
            }
        ],
    )

    discovery = run_visible_catalog_discovery(config=config, manifest=_manifest(), headless=True)

    assert discovery.catalog_url == "https://app.seedtalent.com/catalog"
    assert discovery.items[0].course_title == "Pilot Course"
    assert discovery.items[0].authorized is True


def test_run_visible_catalog_discovery_requires_authenticated_preflight(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTH_EXPIRED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
        ),
    )

    with pytest.raises(ValueError, match="authenticated preflight"):
        run_visible_catalog_discovery(config=config, manifest=_manifest(), headless=True)


def _bundle(config: RuntimePilotConfig):
    selection = PilotCourseSelection(
        courses=[
            PilotCourseSelectionItem(
                course_title="Pilot Course",
                source_url="https://app.seedtalent.com/courses/pilot-course",
                vendor="Vendor A",
                estimated_duration_minutes=30,
            ),
            PilotCourseSelectionItem(
                course_title="Pilot Course Two",
                source_url="https://app.seedtalent.com/courses/pilot-course-two",
                vendor="Vendor A",
                estimated_duration_minutes=45,
            ),
        ]
    )
    plans = build_capture_plans_from_selection(selection=selection, config=config, manifest=_manifest())
    return build_pilot_plan_bundle(selection=selection, config=config, plans=plans)


def test_run_pilot_course_skeleton_marks_preflight_failure(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    base_bundle = _bundle(config)
    bundle = base_bundle.model_copy(update={"plans": [base_bundle.plans[0]]}, deep=True)
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTH_EXPIRED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            account_alias=kwargs["account_alias"],
            current_url="https://app.seedtalent.com/login",
            error_reason="auth_expired",
        ),
    )

    summary = run_pilot_course_skeleton(
        config=config,
        config_path=tmp_path / "runtime.yaml",
        plan_bundle=bundle,
        headless=True,
    )

    assert summary.status == PilotRunStatus.PREFLIGHT_FAILED
    assert summary.failure_bundle_path is not None
    assert Path(summary.run_manifest_path).exists()
    assert Path(summary.batch_manifest_path).exists()


def test_run_pilot_course_skeleton_marks_ready_for_live_capture(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    base_bundle = _bundle(config)
    bundle = base_bundle.model_copy(update={"plans": [base_bundle.plans[0]]}, deep=True)
    preflight_path = tmp_path / "artifacts" / "preflight.png"
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    preflight_path.write_text("preflight", encoding="utf-8")
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTHENTICATED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            account_alias=kwargs["account_alias"],
            current_url="https://app.seedtalent.com/catalog",
            screenshot_uri=str(preflight_path),
        ),
    )

    summary = run_pilot_course_skeleton(
        config=config,
        config_path=tmp_path / "runtime.yaml",
        plan_bundle=bundle,
        course_url=bundle.plans[0].source_url,
        headless=True,
    )

    assert summary.status == PilotRunStatus.READY_FOR_LIVE_CAPTURE
    assert summary.qa_readiness_status == "ready_for_live_capture"


def test_run_pilot_batch_skeleton_blocks_runs_on_batch_preflight_failure(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    bundle = _bundle(config)
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTH_EXPIRED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            current_url="https://app.seedtalent.com/login",
            error_reason="auth_expired",
        ),
    )

    batch_summary, scheduler_summary = run_pilot_batch_skeleton(
        config=config,
        config_path=tmp_path / "runtime.yaml",
        plan_bundle=bundle,
        headless=True,
    )

    assert batch_summary.status == PilotBatchStatus.PREFLIGHT_FAILED
    assert batch_summary.counts.blocked_by_auth_count == 2
    assert scheduler_summary.blocked_by_auth_count == 2


def test_run_pilot_batch_skeleton_marks_runs_ready_after_authenticated_preflight(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    bundle = _bundle(config)
    monkeypatch.setattr(
        "som_seedtalent_capture.pilot_runtime.run_auth_preflight",
        lambda **kwargs: AuthPreflightResult(
            mode=AuthMode.MANUAL_STORAGE_STATE,
            status=AuthPreflightStatus.AUTHENTICATED,
            checked_base_url=kwargs["base_url"],
            storage_state_path=str(kwargs["storage_state_path"]),
            current_url="https://app.seedtalent.com/catalog",
        ),
    )

    batch_summary, scheduler_summary = run_pilot_batch_skeleton(
        config=config,
        config_path=tmp_path / "runtime.yaml",
        plan_bundle=bundle,
        headless=True,
    )

    assert batch_summary.status == PilotBatchStatus.READY_FOR_LIVE_CAPTURE
    assert batch_summary.counts.ready_for_live_capture_count == 2
    assert scheduler_summary.ready_for_live_capture_count == 2
