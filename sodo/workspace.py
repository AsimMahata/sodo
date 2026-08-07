"""
Workspace manager for sodo.

A workspace is marked by a `.sodo` directory. It acts like `.git` for media files.
All downloads within a workspace are tracked via relative paths so the entire
folder can be moved to another drive without breaking the registry.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(s: str) -> str:
    import re
    s = s.lower()
    s = s.replace("\uff5c", "")
    return re.sub(r"[\s|_\-\(\)\[\]]+", "", s)


# ---------------------------------------------------------------------------
# Workspace Discovery & Init
# ---------------------------------------------------------------------------

def find_workspace(start_path: Path | None = None) -> Path | None:
    """Walk up the directory tree to find a .sodo folder. Return the workspace root."""
    current = (start_path or Path.cwd()).resolve()
    for _ in range(50):  # limit depth just in case
        sodo_dir = current / ".sodo"
        if sodo_dir.is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def init_workspace(target_dir: Path) -> Path:
    """Create a .sodo folder for a local workspace. Returns the .sodo path."""
    target_dir = target_dir.resolve()
    sodo_dir = target_dir / ".sodo"
    sodo_dir.mkdir(parents=True, exist_ok=True)
    return sodo_dir
