"""Download history for sodo.

Records are stored in:
  Windows  →  %APPDATA%\\sodo\\history.json
  Other    →  ~/.local/share/sodo/history.json

JSON structure::

    {
      "<cleaned_url>": {
        "<config_key>": {
          "title": "Song Title Here",
          "folder": "C:\\Users\\asim\\Music",
          "downloaded_at": "2026-06-23T14:00:00Z"
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class HistoryEntry(TypedDict, total=False):
    """All fields optional so old records without 'title' still load cleanly."""
    title: str
    folder: str
    downloaded_at: str


# ---------------------------------------------------------------------------
# Storage location
# ---------------------------------------------------------------------------

def _sodo_dir() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "sodo"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "sodo"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "sodo"
    return Path.home() / ".local" / "share" / "sodo"


SODO_DIR: Path = _sodo_dir()
HISTORY_FILE: Path = SODO_DIR / "history.json"


# ---------------------------------------------------------------------------
# Internal I/O
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    SODO_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_config_key(*, fmt: str = "mp3", output_dir: Path) -> str:
    """Build a key encoding format + output folder.

    Example:  ``mp3|C:\\Users\\asim\\Music``
    """
    return f"{fmt}|{output_dir.resolve()}"


def was_downloaded(url: str, config_key: str) -> HistoryEntry | None:
    """Return the history entry if already downloaded with this config, else None."""
    data = _load()
    return data.get(url, {}).get(config_key)  # type: ignore[return-value]


def was_downloaded_globally(url: str, config_key: str) -> HistoryEntry | None:
    """Always check the global master history, ignoring any local workspace overrides."""
    g_dir = _sodo_dir()
    g_file = g_dir / "history.json"
    if not g_file.exists():
        return None
    try:
        data = json.loads(g_file.read_text(encoding="utf-8"))
        url_data = data.get(url)
        if not url_data:
            return None
        # Return the first entry we find for this URL, regardless of the folder/config it was downloaded to.
        # This prevents the exact same URL from being downloaded into multiple different workspaces.
        first_key = next(iter(url_data))
        return url_data[first_key]
    except Exception:
        return None


def record_download(
    url: str,
    config_key: str,
    output_dir: Path,
    *,
    title: str = "",
) -> None:
    """Write a successful download record to the history file."""
    data = _load()
    if url not in data:
        data[url] = {}
    data[url][config_key] = {
        "title": title,
        "folder": str(output_dir.resolve()),
        "downloaded_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _save(data)


def update_title(url: str, config_key: str, title: str) -> None:
    """Patch a single record's title in-place."""
    data = _load()
    if url in data and config_key in data[url]:
        data[url][config_key]["title"] = title
        _save(data)


def load_all() -> list[dict]:
    """Return every history record as a flat list of dicts, newest first.

    Each item has keys: url, fmt, folder, downloaded_at, title.
    """
    data = _load()
    records: list[dict] = []
    for url, configs in data.items():
        for config_key, entry in configs.items():
            parts = config_key.split("|", 1)
            fmt = parts[0] if len(parts) == 2 else config_key
            records.append(
                {
                    "url": url,
                    "config_key": config_key,
                    "fmt": fmt,
                    "title": entry.get("title", ""),
                    "folder": entry.get("folder", ""),
                    "downloaded_at": entry.get("downloaded_at", ""),
                }
            )
    records.sort(key=lambda r: r["downloaded_at"], reverse=True)
    return records
