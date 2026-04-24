from __future__ import annotations

import os
from pathlib import Path


def artifact_root() -> Path:
    """Return the local artifact root for development.

    Production should use object storage. This helper is intentionally simple for the MVP.
    """
    return Path(os.environ.get("CAPTURE_ARTIFACT_ROOT", "./captures")).resolve()
