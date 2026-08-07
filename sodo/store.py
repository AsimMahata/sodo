"""
Persistent data stores for sodo: log, queue, and todo.

All files live alongside history.json in SODO_DIR:
  log.json   – every download attempt (ok / fail)
  queue.json – URLs waiting to be downloaded
  todo.json  – freeform reminder notes
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .history import SODO_DIR

LOG_FILE   = SODO_DIR / "log.json"
QUEUE_FILE = SODO_DIR / "queue.json"
TODO_FILE  = SODO_DIR / "todo.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_id(items: list[dict]) -> int:
    return (max((i.get("id", 0) for i in items), default=0)) + 1


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(path: Path, data: list[dict]) -> None:
    SODO_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

def log_append(
    *,
    url: str,
    status: str,          # "ok" | "fail"
    title: str = "",
    folder: str = "",
    filepath: str = "",   # full path incl. filename + extension
    workspace: str = "",  # path to .sodo root, or "untracked"
    error: str = "",
    force_id: int | None = None,
) -> int:
    """Append a download attempt entry to the log. Returns the assigned ID."""
    entries = _load(LOG_FILE)
    new_id = force_id if force_id is not None else _next_id(entries)
    entries.append({
        "id":        new_id,
        "url":       url,
        "title":     title,
        "folder":    folder,
        "filepath":  filepath,          # e.g. C:\Music\Jane Mon.mp3
        "workspace": workspace,
        "status":    status,
        "error":     error,
        "timestamp": _now(),
    })
    _save(LOG_FILE, entries)
    return new_id


def log_mark_ok(log_id: int, *, title: str = "") -> None:
    """Mark an existing log entry as succeeded (after a successful retry)."""
    entries = _load(LOG_FILE)
    for e in entries:
        if e.get("id") == log_id:
            e["status"] = "ok"
            e["error"]  = ""
            if title:
                e["title"] = title
            break
    _save(LOG_FILE, entries)


def log_fails() -> list[dict]:
    """Latest-entry-per-URL filtered to status == 'fail'."""
    entries = _load(LOG_FILE)
    latest: dict[str, dict] = {}
    for e in entries:
        if url := e.get("url"):
            latest[url] = e
    return [e for e in latest.values() if e.get("status") == "fail"]


def log_clear_fails() -> int:
    """Remove all 'fail' entries from the log. Returns count removed."""
    entries = _load(LOG_FILE)
    original_len = len(entries)
    new_entries = [e for e in entries if e.get("status") != "fail"]
    if len(new_entries) != original_len:
        _save(LOG_FILE, new_entries)
    return original_len - len(new_entries)


def log_list_all(n: int | None = None) -> list[dict]:
    """Return all log entries, newest first. Optionally limited to n."""
    entries = _load(LOG_FILE)
    entries_sorted = list(reversed(entries))   # newest first
    return entries_sorted[:n] if n else entries_sorted


def log_update_entries() -> dict[str, int]:
    """Repair log entries in-place. Returns counts of what was fixed.

    Repairs
    -------
    1. Missing filepath: scan the folder, normalize both title and filename
       to handle yt-dlp's Windows quirk of replacing ``|`` with ``｜`` (U+FF5C).
    2. filepath exists in record but file is gone: mark status as 'missing'.
    """
    import os
    import re

    _MEDIA_EXT = {
        ".mp3", ".mp4", ".flac", ".wav", ".m4a",
        ".opus", ".ogg", ".webm", ".aac", ".wma",
    }

    def _norm(s: str) -> str:
        s = s.lower()
        s = s.replace("\uff5c", "")          # full-width pipe ｜ → gone
        s = re.sub(r"[\s|_\-\(\)\[\]]+", "", s)  # strip separators
        return s

    entries  = _load(LOG_FILE)
    fixed_fp = 0
    marked   = 0

    for e in entries:
        if e.get("status") != "ok":
            continue

        fp = e.get("filepath", "")

        # already have a path → just check it still exists
        if fp:
            if not os.path.exists(fp):
                e["status"] = "missing"
                marked += 1
            continue

        # no path → scan the folder
        folder = e.get("folder", "")
        title  = e.get("title", "")
        if not folder or not os.path.isdir(folder):
            continue

        needle = _norm(title)[:35]
        if not needle:
            continue

        for fname in os.listdir(folder):
            if Path(fname).suffix.lower() not in _MEDIA_EXT:
                continue
            stem = _norm(Path(fname).stem)
            if stem.startswith(needle[:30]) or needle[:30].startswith(stem[:30]):
                e["filepath"] = str(Path(folder) / fname)
                fixed_fp += 1
                break

    _save(LOG_FILE, entries)
    return {"fixed_filepath": fixed_fp, "marked_missing": marked}





def log_missing() -> list[dict]:
    """Return all global log entries where status is 'missing' (latest per URL)."""
    entries = _load(LOG_FILE)
    latest: dict[str, dict] = {}
    for e in entries:
        if url := e.get("url"):
            latest[url] = e
    return [e for e in latest.values() if e.get("status") == "missing"]


def log_summary() -> dict[str, Any]:
    entries   = _load(LOG_FILE)
    total     = len(entries)
    ok_count  = sum(1 for e in entries if e.get("status") == "ok")
    by_folder: dict[str, int] = {}
    for e in entries:
        if e.get("status") == "ok":
            folder = e.get("folder", "unknown")
            by_folder[folder] = by_folder.get(folder, 0) + 1
    return {
        "total":     total,
        "ok":        ok_count,
        "fail":      total - ok_count,
        "by_folder": by_folder,
    }


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------

def queue_add(urls: list[str]) -> int:
    """Add URLs to the queue (skips duplicates). Returns count added."""
    items    = _load(QUEUE_FILE)
    existing = {item["url"] for item in items}
    added    = 0
    for url in urls:
        if url not in existing:
            items.append({"id": _next_id(items), "url": url, "added_at": _now()})
            existing.add(url)
            added += 1
    _save(QUEUE_FILE, items)
    return added


def queue_list(n: int | None = None) -> list[dict]:
    items = _load(QUEUE_FILE)
    return items[:n] if n else items


def queue_pop(n: int | None = None) -> list[dict]:
    """Remove and return up to n items from the front; saves remainder."""
    items    = _load(QUEUE_FILE)
    to_run   = items[:n] if n else items[:]
    _save(QUEUE_FILE, items[n:] if n else [])
    return to_run


def queue_size() -> int:
    return len(_load(QUEUE_FILE))


# ---------------------------------------------------------------------------
# Todo
# ---------------------------------------------------------------------------

def todo_add(note: str) -> int:
    """Append a note; returns its 1-based display index."""
    items = _load(TODO_FILE)
    items.append({"id": _next_id(items), "note": note.strip(), "added_at": _now()})
    _save(TODO_FILE, items)
    return len(items)


def todo_list() -> list[dict]:
    return _load(TODO_FILE)


def todo_clear(n: int | None = None) -> int:
    """Remove first n todos (or all). Returns count removed."""
    items = _load(TODO_FILE)
    if not n:
        removed = len(items)
        _save(TODO_FILE, [])
    else:
        removed = min(n, len(items))
        _save(TODO_FILE, items[removed:])
    return removed


def todo_drop(indices: list[int]) -> int:
    """Drop todos by 1-based display index. Returns count removed."""
    items  = _load(TODO_FILE)
    idx_set = set(indices)
    kept   = [item for i, item in enumerate(items, 1) if i not in idx_set]
    _save(TODO_FILE, kept)
    return len(items) - len(kept)
