from pathlib import Path

import pytest

from som_seedtalent_capture.auth import AuthMode, AuthPreflightResult, AuthPreflightStatus
from som_seedtalent_capture.config import ExternalPathConfig, PilotCourseSelection, PilotCourseSelectionItem, RuntimePilotConfig, SelectorTuningConfig
from som_seedtalent_capture.permissions import PermissionManifest
from som_seedtalent_capture.pilot_runtime import (
    build_capture_plans_from_selection,
    build_pilot_plan_bundle,
    prepare_auth_bootstrap,
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
