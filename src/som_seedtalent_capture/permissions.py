from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PiiPolicy(BaseModel):
    learner_report_data_separate_from_training_content: bool = True
    do_not_embed_raw_employee_names: bool = True
    hash_employee_identifiers: bool = True


class AllowedAccount(BaseModel):
    alias: str
    purpose: str
    notes: str | None = None


class VendorPermission(BaseModel):
    vendor_name: str = "*"
    permission_status: str = "authorized_by_contract_or_vendor_permission"
    scope: str = "covered_seedtalent_training_content"


class PermissionManifest(BaseModel):
    permission_manifest_id: str
    permission_basis: str = "seedtalent_contract_full_use"
    contract_reference: str
    effective_date: str | None = None
    expires_at: str | None = None
    source_platform: str = "seedtalent"
    source_base_url: str = "https://app.seedtalent.com"
    default_rights_status: str = "seedtalent_contract_full_use"
    ai_use_allowed: bool = True
    derivative_use_allowed: bool = True
    internal_training_use_allowed: bool = True
    screen_capture_allowed: bool = True
    visible_dom_capture_allowed: bool = True
    audio_capture_allowed: bool = True
    video_capture_allowed: bool = True
    quiz_capture_allowed: bool = True
    report_capture_allowed: bool = True
    allowed_accounts: list[AllowedAccount] = Field(default_factory=list)
    allowed_vendors: list[VendorPermission] = Field(default_factory=lambda: [VendorPermission()])
    allowed_course_patterns: list[str] = Field(default_factory=lambda: ["*"])
    excluded_paths: list[str] = Field(default_factory=list)
    pii_policy: PiiPolicy = Field(default_factory=PiiPolicy)
    notes: str | None = None


@dataclass(frozen=True)
class AuthorizationDecision:
    authorized: bool
    permission_basis: str
    rights_status: str
    reason: str
    flags: tuple[str, ...] = ()


def _simple_yaml_load(path: Path) -> dict[str, Any]:
    """Tiny YAML-ish loader fallback for the example manifest.

    Codex should replace this with PyYAML or ruamel.yaml when adding real config
    support. This fallback intentionally supports only the simple example shape.
    """
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only when yaml absent
        raise RuntimeError(
            "Install PyYAML or replace _simple_yaml_load with the project's config loader"
        ) from exc
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("permission manifest must be a mapping")
    return payload


def load_permission_manifest(path: str | Path) -> PermissionManifest:
    payload = _simple_yaml_load(Path(path))
    return PermissionManifest.model_validate(payload)


def authorize_capture(
    *,
    url: str,
    vendor: str | None,
    course_title: str | None,
    manifest: PermissionManifest,
) -> AuthorizationDecision:
    flags: list[str] = []

    if manifest.source_base_url and not url.startswith(manifest.source_base_url):
        return AuthorizationDecision(
            authorized=False,
            permission_basis=manifest.permission_basis,
            rights_status="restricted",
            reason="url_outside_approved_source_base_url",
            flags=("url_outside_scope",),
        )

    for excluded in manifest.excluded_paths:
        if excluded and excluded in url:
            return AuthorizationDecision(
                authorized=False,
                permission_basis=manifest.permission_basis,
                rights_status="restricted",
                reason="url_matches_excluded_path",
                flags=("excluded_path",),
            )

    course = course_title or ""
    if manifest.allowed_course_patterns:
        if not any(fnmatch(course, pattern) for pattern in manifest.allowed_course_patterns):
            flags.append("course_pattern_not_matched")

    if vendor:
        vendor_ok = any(
            perm.vendor_name == "*" or perm.vendor_name.lower() == vendor.lower()
            for perm in manifest.allowed_vendors
        )
        if not vendor_ok:
            flags.append("vendor_not_in_manifest")

    if flags:
        return AuthorizationDecision(
            authorized=False,
            permission_basis=manifest.permission_basis,
            rights_status="unknown",
            reason="manifest_scope_not_confirmed",
            flags=tuple(flags),
        )

    return AuthorizationDecision(
        authorized=True,
        permission_basis=manifest.permission_basis,
        rights_status=manifest.default_rights_status,
        reason="covered_by_permission_manifest",
        flags=(),
    )
