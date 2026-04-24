from __future__ import annotations

from pathlib import Path
from typing import Protocol

from som_seedtalent_capture.config import validate_external_runtime_path, validate_path_within_root
from som_seedtalent_capture.permissions import PermissionManifest, load_permission_manifest


class RuntimeManifestLoader(Protocol):
    def load(
        self,
        *,
        manifest_path: str | Path,
        repo_root: str | Path,
        secret_root: str | Path | None = None,
    ) -> PermissionManifest:
        ...


def validate_runtime_manifest_path(manifest_path: str | Path, repo_root: str | Path) -> Path:
    resolved_path = Path(manifest_path).expanduser().resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Runtime permission manifest not found: {resolved_path}")
    if not resolved_path.is_file():
        raise ValueError(f"Runtime permission manifest must be a file: {resolved_path}")
    if not validate_external_runtime_path(resolved_path, repo_root):
        raise ValueError("Runtime permission manifest must live outside the repository")
    return resolved_path


class FileSystemRuntimeManifestLoader:
    def load(
        self,
        *,
        manifest_path: str | Path,
        repo_root: str | Path,
        secret_root: str | Path | None = None,
    ) -> PermissionManifest:
        resolved_path = validate_runtime_manifest_path(manifest_path, repo_root)
        if secret_root is not None and not validate_path_within_root(resolved_path, secret_root):
            raise ValueError("Runtime permission manifest must live under the configured secret root")
        return load_permission_manifest(resolved_path)


def load_runtime_permission_manifest(manifest_path: str | Path, repo_root: str | Path) -> PermissionManifest:
    return FileSystemRuntimeManifestLoader().load(manifest_path=manifest_path, repo_root=repo_root)
