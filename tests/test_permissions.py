from pathlib import Path

from som_seedtalent_capture.models import RightsStatus
from som_seedtalent_capture.permissions import (
    AuthorizationStatus,
    PermissionManifest,
    VendorPermission,
    VendorPermissionStatus,
    authorize_capture,
    load_permission_manifest,
)


def test_permission_manifest_authorizes_seedtalent_course():
    manifest = PermissionManifest(
        permission_manifest_id="test",
        contract_reference="test-contract",
        source_base_url="https://app.seedtalent.com",
        allowed_course_patterns=["*"],
    )
    decision = authorize_capture(
        url="https://app.seedtalent.com/courses/example",
        vendor="Any Vendor",
        course_title="Example Course",
        manifest=manifest,
    )
    assert decision.authorized is True
    assert decision.status == AuthorizationStatus.AUTHORIZED
    assert decision.rights_status == RightsStatus.SEEDTALENT_CONTRACT_FULL_USE
    assert decision.matched_course_pattern == "*"


def test_permission_manifest_blocks_excluded_paths():
    manifest = PermissionManifest(
        permission_manifest_id="test",
        contract_reference="test-contract",
        source_base_url="https://app.seedtalent.com",
        excluded_paths=["/billing"],
    )
    decision = authorize_capture(
        url="https://app.seedtalent.com/billing",
        vendor=None,
        course_title=None,
        manifest=manifest,
    )
    assert decision.authorized is False
    assert decision.status == AuthorizationStatus.RESTRICTED
    assert "excluded_path" in decision.flags


def test_permission_manifest_returns_unknown_for_unmatched_vendor():
    manifest = PermissionManifest(
        permission_manifest_id="test",
        contract_reference="test-contract",
        allowed_vendors=[VendorPermission(vendor_name="Vendor A")],
    )
    decision = authorize_capture(
        url="https://app.seedtalent.com/courses/example",
        vendor="Vendor B",
        course_title="Example Course",
        manifest=manifest,
    )
    assert decision.authorized is False
    assert decision.status == AuthorizationStatus.UNKNOWN
    assert decision.rights_status == RightsStatus.UNKNOWN
    assert "vendor_not_in_manifest" in decision.flags


def test_permission_manifest_returns_unknown_for_unmatched_course_pattern():
    manifest = PermissionManifest(
        permission_manifest_id="test",
        contract_reference="test-contract",
        allowed_course_patterns=["Onboarding *"],
    )
    decision = authorize_capture(
        url="https://app.seedtalent.com/courses/example",
        vendor="Any Vendor",
        course_title="Compliance 101",
        manifest=manifest,
    )
    assert decision.authorized is False
    assert decision.status == AuthorizationStatus.UNKNOWN
    assert "course_pattern_not_matched" in decision.flags


def test_permission_manifest_blocks_outside_source_base_url():
    manifest = PermissionManifest(
        permission_manifest_id="test",
        contract_reference="test-contract",
        source_base_url="https://app.seedtalent.com",
    )
    decision = authorize_capture(
        url="https://example.com/courses/example",
        vendor="Any Vendor",
        course_title="Example Course",
        manifest=manifest,
    )
    assert decision.status == AuthorizationStatus.RESTRICTED
    assert decision.rights_status == RightsStatus.RESTRICTED
    assert "url_outside_scope" in decision.flags


def test_permission_manifest_blocks_vendor_marked_restricted():
    manifest = PermissionManifest(
        permission_manifest_id="test",
        contract_reference="test-contract",
        allowed_vendors=[
            VendorPermission(
                vendor_name="Restricted Vendor",
                permission_status=VendorPermissionStatus.RESTRICTED,
            )
        ],
    )
    decision = authorize_capture(
        url="https://app.seedtalent.com/courses/example",
        vendor="Restricted Vendor",
        course_title="Example Course",
        manifest=manifest,
    )
    assert decision.status == AuthorizationStatus.RESTRICTED
    assert "vendor_restricted" in decision.flags


def test_load_permission_manifest_reads_example_yaml():
    manifest = load_permission_manifest(Path("config/permission_manifest.example.yaml"))
    assert manifest.permission_basis == "seedtalent_contract_full_use"
    assert manifest.default_rights_status == RightsStatus.SEEDTALENT_CONTRACT_FULL_USE
    assert manifest.allowed_accounts[0].alias == "seedtalent-capture-bot"
