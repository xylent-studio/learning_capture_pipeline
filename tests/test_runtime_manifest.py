from pathlib import Path

import pytest

from som_seedtalent_capture.runtime_manifest import FileSystemRuntimeManifestLoader, validate_runtime_manifest_path


def _write_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "permission_manifest_id: runtime-test",
                "contract_reference: runtime-contract",
                "source_base_url: https://app.seedtalent.com",
                "allowed_course_patterns:",
                "  - '*'",
            ]
        ),
        encoding="utf-8",
    )


def test_validate_runtime_manifest_path_requires_external_file(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    manifest_path = repo_root / "config" / "permission_manifest.yaml"
    _write_manifest(manifest_path)

    with pytest.raises(ValueError):
        validate_runtime_manifest_path(manifest_path, repo_root)


def test_filesystem_runtime_manifest_loader_requires_secret_root_membership(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    secret_root = tmp_path / "secrets"
    manifest_path = tmp_path / "outside" / "permission_manifest.yaml"
    _write_manifest(manifest_path)

    loader = FileSystemRuntimeManifestLoader()

    with pytest.raises(ValueError):
        loader.load(manifest_path=manifest_path, repo_root=repo_root, secret_root=secret_root)


def test_filesystem_runtime_manifest_loader_loads_external_manifest(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    secret_root = tmp_path / "secrets"
    manifest_path = secret_root / "manifests" / "permission_manifest.yaml"
    _write_manifest(manifest_path)

    manifest = FileSystemRuntimeManifestLoader().load(
        manifest_path=manifest_path,
        repo_root=repo_root,
        secret_root=secret_root,
    )

    assert manifest.permission_manifest_id == "runtime-test"
    assert manifest.permission_basis == "seedtalent_contract_full_use"
