from som_seedtalent_capture.permissions import PermissionManifest, authorize_capture


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
    assert decision.rights_status == "seedtalent_contract_full_use"


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
    assert "excluded_path" in decision.flags
