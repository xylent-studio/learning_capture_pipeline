from __future__ import annotations

from datetime import date
from enum import StrEnum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from som_seedtalent_capture.models import RightsStatus


class AuthorizationStatus(StrEnum):
    AUTHORIZED = "authorized"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"


class VendorPermissionStatus(StrEnum):
    AUTHORIZED = "authorized_by_contract_or_vendor_permission"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class PiiPolicy(BaseModel):
    learner_report_data_separate_from_training_content: bool = True
    do_not_embed_raw_employee_names: bool = True
    hash_employee_identifiers: bool = True


class AccountAlias(BaseModel):
    alias: str
    purpose: str
    notes: str | None = None


class VendorPermission(BaseModel):
    vendor_name: str = "*"
    permission_status: VendorPermissionStatus = VendorPermissionStatus.AUTHORIZED
    scope: str = "covered_seedtalent_training_content"


class PermissionManifest(BaseModel):
    permission_manifest_id: str
    permission_basis: str = "seedtalent_contract_full_use"
    contract_reference: str
    effective_date: date | None = None
    expires_at: date | None = None
    source_platform: str = "seedtalent"
    source_base_url: str = "https://app.seedtalent.com"
    default_rights_status: RightsStatus = RightsStatus.SEEDTALENT_CONTRACT_FULL_USE
    ai_use_allowed: bool = True
    derivative_use_allowed: bool = True
    internal_training_use_allowed: bool = True
    screen_capture_allowed: bool = True
    visible_dom_capture_allowed: bool = True
    audio_capture_allowed: bool = True
    video_capture_allowed: bool = True
    quiz_capture_allowed: bool = True
    report_capture_allowed: bool = True
    allowed_accounts: list[AccountAlias] = Field(default_factory=list)
    allowed_vendors: list[VendorPermission] = Field(default_factory=lambda: [VendorPermission()])
    allowed_course_patterns: list[str] = Field(default_factory=lambda: ["*"])
    excluded_paths: list[str] = Field(default_factory=list)
    pii_policy: PiiPolicy = Field(default_factory=PiiPolicy)
    notes: str | None = None

    @field_validator("allowed_course_patterns")
    @classmethod
    def validate_course_patterns(cls, value: list[str]) -> list[str]:
        cleaned = [entry.strip() for entry in value if entry and entry.strip()]
        if not cleaned:
            raise ValueError("allowed_course_patterns must include at least one value")
        return cleaned

    @field_validator("excluded_paths")
    @classmethod
    def validate_excluded_paths(cls, value: list[str]) -> list[str]:
        return [entry.strip() for entry in value if entry and entry.strip()]

    @property
    def parsed_source_base_url(self) -> tuple[str, str, str]:
        parsed = urlparse(self.source_base_url)
        return parsed.scheme, parsed.netloc, parsed.path.rstrip("/")


class AuthorizationDecision(BaseModel):
    status: AuthorizationStatus
    permission_basis: str
    rights_status: RightsStatus
    reason: str
    flags: tuple[str, ...] = ()
    matched_vendor: str | None = None
    matched_course_pattern: str | None = None

    @property
    def authorized(self) -> bool:
        return self.status == AuthorizationStatus.AUTHORIZED

    @property
    def restricted(self) -> bool:
        return self.status == AuthorizationStatus.RESTRICTED


def _simple_yaml_load(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only when yaml absent
        raise RuntimeError("Install PyYAML to load permission manifests") from exc
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("permission manifest must be a mapping")
    return payload


def load_permission_manifest(path: str | Path) -> PermissionManifest:
    payload = _simple_yaml_load(Path(path))
    return PermissionManifest.model_validate(payload)


def _url_is_in_scope(url: str, manifest: PermissionManifest) -> bool:
    parsed_url = urlparse(url)
    scheme, netloc, base_path = manifest.parsed_source_base_url
    if parsed_url.scheme != scheme or parsed_url.netloc != netloc:
        return False
    if base_path and not parsed_url.path.startswith(base_path):
        return False
    return True


def _match_excluded_path(url: str, manifest: PermissionManifest) -> str | None:
    parsed_path = urlparse(url).path
    for excluded in manifest.excluded_paths:
        if fnmatch(parsed_path, excluded) or parsed_path.startswith(excluded):
            return excluded
    return None


def _match_vendor(vendor: str | None, manifest: PermissionManifest) -> VendorPermission | None:
    if not vendor:
        return next((perm for perm in manifest.allowed_vendors if perm.vendor_name == "*"), None)
    vendor_lower = vendor.lower()
    for permission in manifest.allowed_vendors:
        if permission.vendor_name == "*" or permission.vendor_name.lower() == vendor_lower:
            return permission
    return None


def _match_course_pattern(course_title: str | None, manifest: PermissionManifest) -> str | None:
    if course_title is None:
        return "*" if "*" in manifest.allowed_course_patterns else None
    for pattern in manifest.allowed_course_patterns:
        if fnmatch(course_title, pattern):
            return pattern
    return None


def authorize_capture(
    *,
    url: str,
    vendor: str | None,
    course_title: str | None,
    manifest: PermissionManifest,
) -> AuthorizationDecision:
    if not _url_is_in_scope(url, manifest):
        return AuthorizationDecision(
            status=AuthorizationStatus.RESTRICTED,
            permission_basis=manifest.permission_basis,
            rights_status=RightsStatus.RESTRICTED,
            reason="url_outside_approved_source_base_url",
            flags=("url_outside_scope",),
        )

    excluded_path = _match_excluded_path(url, manifest)
    if excluded_path:
        return AuthorizationDecision(
            status=AuthorizationStatus.RESTRICTED,
            permission_basis=manifest.permission_basis,
            rights_status=RightsStatus.RESTRICTED,
            reason="url_matches_excluded_path",
            flags=("excluded_path",),
        )

    vendor_permission = _match_vendor(vendor, manifest)
    if vendor_permission is None:
        return AuthorizationDecision(
            status=AuthorizationStatus.UNKNOWN,
            permission_basis=manifest.permission_basis,
            rights_status=RightsStatus.UNKNOWN,
            reason="vendor_not_in_manifest",
            flags=("vendor_not_in_manifest",),
        )

    if vendor_permission.permission_status == VendorPermissionStatus.RESTRICTED:
        return AuthorizationDecision(
            status=AuthorizationStatus.RESTRICTED,
            permission_basis=manifest.permission_basis,
            rights_status=RightsStatus.RESTRICTED,
            reason="vendor_explicitly_restricted",
            flags=("vendor_restricted",),
            matched_vendor=vendor_permission.vendor_name,
        )

    course_pattern = _match_course_pattern(course_title, manifest)
    if course_pattern is None:
        return AuthorizationDecision(
            status=AuthorizationStatus.UNKNOWN,
            permission_basis=manifest.permission_basis,
            rights_status=RightsStatus.UNKNOWN,
            reason="course_pattern_not_matched",
            flags=("course_pattern_not_matched",),
            matched_vendor=vendor_permission.vendor_name,
        )

    return AuthorizationDecision(
        status=AuthorizationStatus.AUTHORIZED,
        permission_basis=manifest.permission_basis,
        rights_status=manifest.default_rights_status,
        reason="covered_by_permission_manifest",
        flags=(),
        matched_vendor=vendor_permission.vendor_name,
        matched_course_pattern=course_pattern,
    )


AllowedAccount = AccountAlias
