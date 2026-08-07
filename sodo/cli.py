"""sodo CLI entry point."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import click

from . import __version__
from .downloader import DEFAULT_FMT, DOWNLOAD_FAIL, DOWNLOAD_OK, DOWNLOAD_SKIPPED, FORMATS, download_audio
from .history import HISTORY_FILE, load_all, make_config_key, update_title
from .store import (
    LOG_FILE, QUEUE_FILE, TODO_FILE,
    log_append, log_fails, log_list_all, log_mark_ok, log_missing, log_summary, log_update_entries,
    queue_add, queue_list, queue_pop, queue_size,
    todo_add, todo_clear, todo_drop, todo_list,
)
from .workspace import _norm, find_workspace, init_workspace

_QS_FRAGMENT = re.compile(r"^[A-Za-z0-9_]+=\S*$")


# ---------------------------------------------------------------------------
# Shared display utils
# ---------------------------------------------------------------------------

def _trunc(s: str, w: int) -> str:
    return (s[: w - 1] + "\u2026") if len(s) > w else s


def _short_folder(folder: str, n: int = 2) -> str:
    p = Path(folder)
    parts = p.parts
    return ("\u2026\\" + "\\".join(parts[-n:])) if len(parts) > n else folder


def _banner() -> None:
    click.echo(
        click.style("  sodo ", fg="cyan", bold=True)
        + click.style(f"v{__version__}", fg="bright_black")
        + "  \u2014 YouTube \u2192 MP3 downloader"
    )
    click.echo("")


def _rule(width: int = 100) -> None:
    click.echo("  " + "\u2500" * width)


def _section(title: str) -> None:
    click.echo(click.style(f"  \u2500\u2500\u2500 {title} ", fg="bright_black") +
               click.style("\u2500" * max(0, 70 - len(title)), fg="bright_black"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_urls(urls: tuple[str, ...]) -> None:
    bad = [u for u in urls if _QS_FRAGMENT.match(u)]
    if not bad:
        return
    real_urls = [u for u in urls if u.startswith(("http://", "https://", "youtu"))]
    click.echo("")
    click.echo(click.style("  [!] PowerShell URL-splitting detected", fg="red", bold=True))
    click.echo(click.style(
        "      PowerShell splits unquoted URLs at every '&' character.\n"
        "      The following were passed as separate arguments instead of\n"
        "      being part of the URL:", fg="yellow"))
    for frag in bad:
        click.echo(click.style(f"        \u2022 {frag}", fg="bright_black"))
    click.echo("")
    click.echo(click.style("  Fix: wrap each URL in quotes:", fg="cyan", bold=True))
    if real_urls:
        base = real_urls[-1]
        sep  = "&" if "?" in base else "?"
        full_url = base + sep + "&".join(bad)
        click.echo(click.style(f'        sodo "{full_url}"', fg="green"))
    click.echo("")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------

def _do_summary() -> None:
    stats = log_summary()
    hist  = load_all()

    _section("Summary")
    click.echo("")
    click.echo(click.style("  Total attempts   : ", fg="bright_black") + click.style(str(stats["total"]), fg="white", bold=True))
    click.echo(click.style("  \u2713 Successful     : ", fg="green")       + click.style(str(stats["ok"]), fg="green", bold=True))
    click.echo(click.style("  \u2717 Failed         : ", fg="red")         + click.style(str(stats["fail"]), fg="red", bold=True))
    click.echo(click.style("  Unique tracks    : ", fg="bright_black") + click.style(str(len(hist)), fg="white"))
    click.echo(click.style("  Queue            : ", fg="bright_black") + click.style(str(queue_size()), fg="cyan"))
    click.echo(click.style("  Todos            : ", fg="bright_black") + click.style(str(len(todo_list())), fg="cyan"))
    click.echo("")

    by_folder = stats["by_folder"]
    if by_folder:
        _section("Per-folder")
        click.echo("")
        sorted_folders = sorted(by_folder.items(), key=lambda x: -x[1])
        for folder, count in sorted_folders:
            short = _short_folder(folder)
            bar   = "\u2588" * min(count, 30)
            click.echo(
                click.style(f"  {short:<35}", fg="cyan")
                + click.style(f"  {count:>4} download(s)  ", fg="white")
                + click.style(bar, fg="green")
            )
        click.echo("")

    _section("Files")
    click.echo("")
    for label, path in [
        ("History", HISTORY_FILE),
        ("Log    ", LOG_FILE),
        ("Queue  ", QUEUE_FILE),
        ("Todos  ", TODO_FILE),
    ]:
        click.echo(click.style(f"  {label} \u2192 ", fg="bright_black") + click.style(str(path), fg="cyan"))
    click.echo("")


def _do_log(n: int | None) -> None:
    """Show the full download log (all attempts, newest first)."""
    entries = log_list_all(n)
    if not entries:
        click.echo(click.style("  No log entries yet.", fg="bright_black"))
        click.echo(click.style("  Download something first, then run: sodo --log", fg="bright_black"))
        return

    label = f"last {n}" if n else "all"
    click.echo(click.style(f"  Log ({label} entries, newest first):", fg="cyan", bold=True))
    click.echo("")

    STATUS_STYLE = {
        "ok":      ("  ✓ ok     ", "green"),
        "fail":    ("  ✗ fail   ", "red"),
        "missing": ("  ▲ missing", "yellow"),
    }

    for e in entries:
        status  = e.get("status", "?")
        label_s, color = STATUS_STYLE.get(status, (f"  {status}", "white"))
        ts       = e.get("timestamp", "")[:19].replace("T", " ")
        title    = _trunc(e.get("title") or "—", 55)
        filepath = e.get("filepath", "")
        folder   = e.get("folder", "")
        url      = _trunc(e.get("url", ""), 60)

        click.echo(click.style(label_s, fg=color, bold=True) + click.style(f"  {ts}", fg="bright_black"))
        click.echo(f"    title   : {title}")
        if filepath:
            click.echo("    file    : " + click.style(filepath, fg="cyan"))
        elif folder:
            click.echo("    folder  : " + click.style(_short_folder(folder), fg="cyan") + click.style("  (no filename captured)", fg="bright_black"))
        if status == "fail":
            click.echo("    error   : " + click.style(_trunc(e.get("error", ""), 80), fg="red"))
        click.echo(click.style(f"    url     : {url}", fg="bright_black"))
        click.echo("")

    click.echo(click.style(f"  {len(entries)} entries shown.  Log file: {LOG_FILE}", fg="bright_black"))
    click.echo(click.style("  Tip: sodo --log --update   to repair missing file paths", fg="bright_black"))
    click.echo("")


def _do_log_update() -> None:
    """Repair log entries: fill missing filepaths, mark deleted files."""
    click.echo(click.style("  Scanning log for repairs…", fg="yellow"))
    result = log_update_entries()
    fixed  = result["fixed_filepath"]
    marked = result["marked_missing"]
    if fixed:
        click.echo(click.style(f"  ✓ Filled filepath for {fixed} entry/entries.", fg="green"))
    if marked:
        click.echo(click.style(f"  ▲ Marked {marked} entry/entries as 'missing' (file deleted).", fg="yellow"))
    if not fixed and not marked:
        click.echo(click.style("  ✓ Nothing to repair.", fg="green"))
    click.echo("")


def _do_fails() -> None:
    fails = log_fails()
    if not fails:
        click.echo(click.style("  \u2713 No failed downloads recorded.", fg="green"))
        return

    click.echo(click.style(f"  {len(fails)} failed download(s):\n", fg="red", bold=True))
    _W_ID   = 4
    _W_DATE = 21
    _W_URL  = 55

    click.echo(
        click.style(f"  {'#':<{_W_ID}}", fg="bright_black")
        + click.style(f"  {'Date':<{_W_DATE}}", fg="bright_black")
        + click.style(f"  {'URL':<{_W_URL}}", fg="bright_black")
        + click.style("  Error", fg="bright_black")
    )
    _rule(110)

    for i, e in enumerate(fails, 1):
        click.echo(
            click.style(f"  {i:<{_W_ID}}", fg="bright_black")
            + click.style(f"  {e.get('timestamp',''):<{_W_DATE}}", fg="white")
            + f"  {_trunc(e.get('url',''), _W_URL):<{_W_URL}}"
            + "  " + click.style(_trunc(e.get("error", ""), 50), fg="red")
        )
    click.echo("")
    click.echo(click.style("  Tip: sodo --retry      (retry all)", fg="bright_black"))
    click.echo(click.style("       sodo --retry 3    (retry top 3)", fg="bright_black"))
    click.echo("")


# ---------------------------------------------------------------------------
# Workspace Commands
# ---------------------------------------------------------------------------

def _do_init(out_dir: Path) -> None:
    ws = find_workspace(out_dir)
    if ws:
        click.echo(click.style(f"  \u2713 Workspace already exists at: {ws}", fg="green"))
        return
    sodo_dir = init_workspace(out_dir)
    click.echo(click.style(f"  \u2713 Initialized empty sodo workspace in: {out_dir}", fg="green"))


def _do_search(query: str, out_dir: Path, is_global: bool) -> None:
    terms = query.split()
    entries = log_list_all()
    normalized_terms = [_norm(t) for t in terms if _norm(t)]
    results = []
    
    for e in entries:
        haystack = _norm(e.get("filepath", "") + " " + e.get("title", ""))
        if all(t in haystack for t in normalized_terms):
            results.append(e)
            
    ws = find_workspace(out_dir)
    scope_name = "Global Log" if is_global else f"workspace: {ws}"
    
    if not results:
        click.echo(click.style(f"  No results found for '{query}' in {scope_name}.", fg="bright_black"))
        return
        
    click.echo(click.style(f"  Found {len(results)} matches for '{query}' in {scope_name}:\n", fg="cyan", bold=True))
    _W_IDX = 4
    _W_TITLE = 40
    click.echo(
        click.style(f"  {'#':<{_W_IDX}}", fg="bright_black")
        + click.style(f"  {'Title':<{_W_TITLE}}", fg="bright_black")
        + click.style("  Absolute Path", fg="bright_black")
    )
    _rule(110)
    
    for i, r in enumerate(results, 1):
        status = " (missing)" if r.get("status") == "missing" else ""
        color = "yellow" if status else "cyan"
        click.echo(
            click.style(f"  {i:<{_W_IDX}}", fg="bright_black")
            + f"  {_trunc(r.get('title') or '—', _W_TITLE):<{_W_TITLE}}"
            + click.style(f"  {r.get('filepath', '')}{status}", fg=color)
        )
    click.echo("")


def _do_sync(out_dir: Path) -> None:
    ws = find_workspace(out_dir)
    if not ws:
        click.echo(click.style("  \u2717 Not in a sodo workspace. Run 'sodo --init' to create one.", fg="red"))
        return
        
    click.echo(click.style("  Scanning workspace for moved files\u2026", fg="yellow"))
    
    _MEDIA_EXT = {".mp3", ".mp4", ".flac", ".wav", ".m4a", ".opus", ".ogg", ".webm", ".aac", ".wma"}
    
    import os
    current_files: dict[str, list[str]] = {}
    for root, _, files in os.walk(ws):
        if ".sodo" in root or ".git" in root:
            continue
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in _MEDIA_EXT:
                stem = _norm(p.stem)
                current_files.setdefault(stem, []).append(str(p))

    local_entries = log_list_all()
    
    fixed = 0
    orphaned = 0
    updates_to_global: dict[str, str] = {}
    
    for e in local_entries:
        if e.get("status") not in ("ok", "missing"):
            continue
            
        old_path = e.get("filepath", "")
        if old_path and Path(old_path).exists():
            continue
            
        title_stem = _norm(e.get("title", ""))[:30]
        old_stem = _norm(Path(old_path).stem)[:30] if old_path else ""
        
        found = False
        for search_stem in (old_stem, title_stem):
            if not search_stem:
                continue
            matches = [p for s, paths in current_files.items() for p in paths if s.startswith(search_stem) or search_stem.startswith(s)]
            if matches:
                e["filepath"] = matches[0]
                e["folder"] = str(Path(matches[0]).parent)
                e["status"] = "ok"
                fixed += 1
                found = True
                updates_to_global[e["url"]] = matches[0]
                break
                
        if not found:
            if e.get("status") != "missing":
                e["status"] = "missing"
                orphaned += 1
                updates_to_global[e["url"]] = ""

    if fixed or orphaned:
        from .store import _save, LOG_FILE
        _save(LOG_FILE, local_entries)
        
    global_fixed = 0
    global_missing = 0
    
    if updates_to_global:
        from .history import _sodo_dir
        g_dir = _sodo_dir()
        g_log = g_dir / "log.json"
        g_hist = g_dir / "history.json"
        
        if g_log.exists():
            from .store import _load, _save
            g_entries = _load(g_log)
            changed_g_log = False
            for ge in g_entries:
                url = ge.get("url")
                if url in updates_to_global:
                    new_fp = updates_to_global[url]
                    if new_fp:
                        if ge.get("filepath") != new_fp:
                            ge["filepath"] = new_fp
                            ge["folder"] = str(Path(new_fp).parent)
                            ge["status"] = "ok"
                            global_fixed += 1
                            changed_g_log = True
                    else:
                        if ge.get("status") != "missing":
                            ge["status"] = "missing"
                            global_missing += 1
                            changed_g_log = True
            if changed_g_log:
                _save(g_log, g_entries)
                
        if g_hist.exists():
            try:
                import json
                h_data = json.loads(g_hist.read_text(encoding="utf-8"))
                changed_h = False
                for url, new_fp in updates_to_global.items():
                    if url in h_data and new_fp:
                        for cfg, details in h_data[url].items():
                            if details.get("filepath") != new_fp:
                                details["filepath"] = new_fp
                                details["folder"] = str(Path(new_fp).parent)
                                changed_h = True
                if changed_h:
                    g_hist.write_text(json.dumps(h_data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

    if fixed:
        click.echo(click.style(f"  \u2713 Fixed {fixed} local broken link(s).", fg="green"))
    if global_fixed:
        click.echo(click.style(f"  \u2713 Updated {global_fixed} absolute path(s) in global log.", fg="green"))
    if orphaned:
        click.echo(click.style(f"  \u25b2 {orphaned} file(s) are missing locally.", fg="yellow"))
    if global_missing:
        click.echo(click.style(f"  \u25b2 {global_missing} file(s) marked as missing in global log.", fg="yellow"))
    if not any([fixed, orphaned, global_fixed, global_missing]):
        click.echo(click.style("  \u2713 Workspace and global log are perfectly synced.", fg="green"))
    click.echo("")


def _do_missing() -> None:
    missing = log_missing()
    if not missing:
        click.echo(click.style("  \u2713 No missing files recorded in global log.", fg="green"))
        return

    click.echo(click.style(f"  {len(missing)} missing file(s):\n", fg="yellow", bold=True))
    _W_ID   = 4
    _W_TITLE = 40
    _W_URL  = 60

    click.echo(
        click.style(f"  {'#':<{_W_ID}}", fg="bright_black")
        + click.style(f"  {'Title':<{_W_TITLE}}", fg="bright_black")
        + click.style("  URL", fg="bright_black")
    )
    _rule(110)

    for i, e in enumerate(missing, 1):
        click.echo(
            click.style(f"  {i:<{_W_ID}}", fg="bright_black")
            + f"  {_trunc(e.get('title') or '—', _W_TITLE):<{_W_TITLE}}"
            + click.style(f"  {_trunc(e.get('url',''), _W_URL)}", fg="white")
        )
    click.echo("")
    click.echo(click.style("  Tip: Copy a URL and use 'sodo --add URL' to requeue it.", fg="bright_black"))
    click.echo("")


def _do_fails_clear(out_dir: Path, skip: bool) -> None:
    ws = find_workspace(out_dir)
    
    # Switch to global
    from . import store, history as hist_mod
    from .history import _sodo_dir
    local_sodo_dir = store.SODO_DIR
    local_log_file = store.LOG_FILE
    
    g_dir = _sodo_dir()
    store.SODO_DIR = g_dir
    store.LOG_FILE = g_dir / "log.json"
    
    global_cleared = store.log_clear_fails()
    
    # Restore local
    store.SODO_DIR = local_sodo_dir
    store.LOG_FILE = local_log_file
    
    local_cleared = 0
    if ws and not skip:
        local_cleared = store.log_clear_fails()
        
    click.echo("")
    if global_cleared:
        click.echo(click.style(f"  \u2713 Cleared {global_cleared} fail(s) from global log.", fg="green"))
    else:
        click.echo(click.style("  \u2713 No fails found in global log.", fg="green"))
        
    if ws and not skip:
        if local_cleared:
            click.echo(click.style(f"  \u2713 Cleared {local_cleared} fail(s) from local workspace.", fg="green"))
        else:
            click.echo(click.style("  \u2713 No fails found in local workspace.", fg="green"))
    click.echo("")


def _do_cluster(is_global: bool) -> None:
    click.echo(click.style("  \u2699 Analyzing history for similar titles...", fg="cyan"))
    
    entries = log_list_all()
    valid_entries = [e for e in entries if e.get("status") in ("ok", "missing") and e.get("title")]
    
    if not valid_entries:
        click.echo(click.style("  No downloaded titles found.", fg="bright_black"))
        return
        
    import difflib
    import re
    
    def _clean_title(t: str) -> str:
        t = re.sub(r'\(.*?\)', '', t)
        t = re.sub(r'\[.*?\]', '', t)
        t = re.sub(r'[^a-zA-Z0-9\s]', ' ', t).lower()
        return " ".join(t.split())
        
    clusters: list[list[dict]] = []
    
    for e in valid_entries:
        title = e["title"]
        ct = _clean_title(title)
        if not ct:
            continue
            
        found_cluster = False
        for cluster in clusters:
            first_e = cluster[0]
            first_ct = _clean_title(first_e["title"])
            
            # Use quick_ratio for speed, then ratio for accuracy
            sm = difflib.SequenceMatcher(None, ct, first_ct)
            if sm.quick_ratio() > 0.70 and sm.ratio() > 0.75:
                cluster.append(e)
                found_cluster = True
                break
                
        if not found_cluster:
            clusters.append([e])
            
    real_clusters = [c for c in clusters if len(c) > 1]
    
    if not real_clusters:
        click.echo(click.style("  \u2713 No similar titles found. Your library is clean!", fg="green"))
        return
        
    click.echo(click.style(f"  Found {len(real_clusters)} potential duplicate cluster(s):\n", fg="yellow", bold=True))
    
    for i, cluster in enumerate(real_clusters, 1):
        click.echo(click.style(f"  Cluster {i}:", fg="cyan", bold=True))
        for e in cluster:
            status = " (missing)" if e.get("status") == "missing" else ""
            color = "yellow" if status else "white"
            click.echo(f"    • {e['title']}")
            click.echo(click.style(f"      {e.get('folder', 'Unknown Folder')}{status}", fg="bright_black"))
            click.echo(click.style(f"      {e.get('url', '')}", fg="blue"))
        click.echo("")
        
    click.echo(click.style("  Review the clusters above and delete any duplicates manually.", fg="bright_black"))
    click.echo("")


def _do_links(out_dir: Path, is_global: bool) -> None:
    entries = log_list_all()
    urls = set()
    
    current_dir_str = str(out_dir.resolve()).lower()
    
    for e in entries:
        if e.get("status") not in ("ok", "missing"):
            continue
            
        url = e.get("url")
        if not url:
            continue
            
        if is_global:
            urls.add(url)
        else:
            import os
            folder = e.get("folder", "").lower()
            # Must be the exact folder or a proper subfolder
            if folder == current_dir_str or folder.startswith(current_dir_str + os.sep):
                urls.add(url)
                
    if urls:
        click.echo(" ".join(urls))
    else:
        click.echo("")


def _do_fails() -> None:
    fails = log_fails()
    if not fails:
        click.echo(click.style("  \u2713 No failed downloads.", fg="green"))
        return
    click.echo(click.style(f"  {len(fails)} failed download(s):\n", fg="red", bold=True))
    _W_ID = 4; _W_URL = 60
    click.echo(
        click.style(f"  {'#':<{_W_ID}}", fg="bright_black")
        + click.style("  URL", fg="bright_black")
    )
    _rule(80)
    for i, e in enumerate(fails, 1):
        click.echo(
            click.style(f"  {i:<{_W_ID}}", fg="bright_black")
            + click.style(f"  {_trunc(e.get('url',''), _W_URL)}", fg="red")
        )
    click.echo("")
    click.echo(click.style("  Retry all fails: sodo --retry", fg="bright_black"))
    click.echo(click.style("  Retry top 3:     sodo --retry 3", fg="bright_black"))
    click.echo("")


def _do_retry(n: int, out_dir: Path, quiet: bool, skip: bool, force: bool) -> None:
    ws = find_workspace(out_dir)
    if not ws and not skip:
        click.echo(click.style("  \u2717 Not inside a .sodo workspace.", fg="red"))
        click.echo(click.style("  Run 'sodo --init' first, or use '--skip' to bypass.", fg="bright_black"))
        sys.exit(1)
        
    ws_str = "untracked" if skip else str(ws)

    fails = log_fails()
    if not fails:
        click.echo(click.style("  \u2713 No failures to retry.", fg="green"))
        return
    batch = fails[:n] if n else fails
    click.echo(click.style(f"  Retrying {len(batch)} failed download(s)\u2026\n", fg="yellow", bold=True))
    urls      = [e["url"] for e in batch]
    id_by_url = {e["url"]: e["id"] for e in batch}

    config_key = make_config_key(fmt="mp3", output_dir=out_dir)
    results    = download_audio(urls, out_dir, quiet=quiet, config_key=config_key, force=force)

    _dual_write_results(results, ws, skip, config_key, out_dir, ws_str)

    for r in results:
        if r["status"] == DOWNLOAD_OK:
            log_mark_ok(id_by_url[r["url"]], title=r.get("title", ""))

    _print_summary(results)


def _do_add(urls: tuple[str, ...]) -> None:
    added = queue_add(list(urls))
    total = queue_size()
    click.echo(click.style(f"  \u2713 Added {added} URL(s) to queue.", fg="green", bold=True))
    click.echo(click.style(f"  Queue now has {total} item(s).  (run: sodo --run)", fg="bright_black"))
    click.echo("")


def _do_queue(n: int | None, full: bool) -> None:
    items = queue_list(n)
    if not items:
        click.echo(click.style("  Queue is empty.  (add: sodo --add URL)", fg="bright_black"))
        return
    label = f"top {n}" if n else "all"
    click.echo(click.style(f"  Queue — {label} of {queue_size()} item(s):\n", fg="cyan", bold=True))
    _W_ID = 4; _W_DATE = 21
    click.echo(
        click.style(f"  {'#':<{_W_ID}}", fg="bright_black")
        + click.style(f"  {'Added':<{_W_DATE}}", fg="bright_black")
        + click.style("  URL", fg="bright_black")
    )
    _rule(90)
    for i, item in enumerate(items, 1):
        click.echo(
            click.style(f"  {i:<{_W_ID}}", fg="bright_black")
            + click.style(f"  {item.get('added_at',''):<{_W_DATE}}", fg="white")
            + "  " + click.style(_trunc(item["url"], 80), fg="cyan")
        )
    click.echo("")
    click.echo(click.style("  Run queue: sodo --run", fg="bright_black"))
    click.echo("")


def _do_run(out_dir: Path, quiet: bool, skip: bool, force: bool) -> None:
    _ensure_ffmpeg()
    ws = find_workspace(out_dir)
    if not ws and not skip:
        click.echo(click.style("  \u2717 Not inside a .sodo workspace.", fg="red"))
        click.echo(click.style("  Run 'sodo --init' first, or use '--skip' to bypass.", fg="bright_black"))
        sys.exit(1)
        
    ws_str = "untracked" if skip else str(ws)

    items = queue_pop()          # empties the queue
    if not items:
        click.echo(click.style("  Queue is empty.", fg="bright_black"))
        return
    click.echo(click.style(f"  Running queue: {len(items)} item(s)\u2026\n", fg="cyan", bold=True))
    urls       = [item["url"] for item in items]
    config_key = make_config_key(fmt="mp3", output_dir=out_dir)
    results    = download_audio(urls, out_dir, quiet=quiet, config_key=config_key, force=force)
    _dual_write_results(results, ws, skip, config_key, out_dir, ws_str)
    _print_summary(results)


def _do_todos(full_flag: bool) -> None:
    items = todo_list()
    if not items:
        click.echo(click.style("  No todos yet.  (add: sodo --todo \"note\")", fg="bright_black"))
        return
    click.echo(click.style(f"  {len(items)} todo(s):\n", fg="cyan", bold=True))
    _W_ID = 4; _W_DATE = 21
    click.echo(
        click.style(f"  {'#':<{_W_ID}}", fg="bright_black")
        + click.style(f"  {'Added':<{_W_DATE}}", fg="bright_black")
        + click.style("  Note", fg="bright_black")
    )
    _rule(90)
    for i, item in enumerate(items, 1):
        click.echo(
            click.style(f"  {i:<{_W_ID}}", fg="bright_black")
            + click.style(f"  {item.get('added_at',''):<{_W_DATE}}", fg="white")
            + "  " + _trunc(item.get("note", ""), 80)
        )
    click.echo("")
    click.echo(click.style("  sodo --todo-clear        clear all", fg="bright_black"))
    click.echo(click.style("  sodo --todo-clear 2      clear top 2", fg="bright_black"))
    click.echo(click.style("  sodo --todo-drop 1 3     drop by index", fg="bright_black"))
    click.echo("")


# ---------------------------------------------------------------------------
# Log helper (called after every download)
# ---------------------------------------------------------------------------

def _log_result(r: dict, workspace: str = "", force_id: int | None = None) -> int | None:
    if r["status"] == DOWNLOAD_SKIPPED:
        return None
    return log_append(
        url=r.get("cleaned") or r["url"],
        status=r["status"],
        title=r.get("title", ""),
        folder=r.get("folder", ""),
        filepath=r.get("filepath", ""),
        workspace=workspace,
        error=r.get("error", ""),
        force_id=force_id,
    )


def _dual_write_results(results: list[dict], ws: Path | None, skip: bool, config_key: str, out_dir: Path, ws_str: str) -> None:
    for r in results:
        if ws and not skip:
            from . import store
            from . import history as hist_mod
            from .history import _sodo_dir
            
            # 1. Switch to global
            local_hist_file = hist_mod.HISTORY_FILE
            local_sodo_dir = hist_mod.SODO_DIR
            local_log_file = store.LOG_FILE
            
            g_dir = _sodo_dir()
            hist_mod.SODO_DIR = g_dir
            hist_mod.HISTORY_FILE = g_dir / "history.json"
            store.SODO_DIR = g_dir
            store.LOG_FILE = g_dir / "log.json"
            
            # 2. Write to global and capture the true global ID
            if r["status"] == DOWNLOAD_OK:
                hist_mod.record_download(r.get("cleaned") or r["url"], config_key, out_dir, title=r.get("title", ""))
            
            global_id = _log_result(r, ws_str)
            
            # 3. Restore local
            hist_mod.SODO_DIR = local_sodo_dir
            hist_mod.HISTORY_FILE = local_hist_file
            store.SODO_DIR = local_sodo_dir
            store.LOG_FILE = local_log_file
            
            # 4. Write to local, forcing the ID to match global
            _log_result(r, ws_str, force_id=global_id)
        else:
            # Not in a workspace or skipped, just write normally
            _log_result(r, ws_str)


# ---------------------------------------------------------------------------
# Print summary (post-download)
# ---------------------------------------------------------------------------

def _print_summary(results: list[dict]) -> None:
    ok      = sum(1 for r in results if r["status"] == DOWNLOAD_OK)
    fail    = sum(1 for r in results if r["status"] == DOWNLOAD_FAIL)
    skipped = sum(1 for r in results if r["status"] == DOWNLOAD_SKIPPED)
    click.echo("")
    if ok:
        click.echo(click.style(f"  \u2713 {ok} downloaded successfully", fg="green", bold=True))
    if fail:
        click.echo(click.style(f"  \u2717 {fail} failed", fg="red", bold=True))
    if skipped:
        click.echo(click.style(f"  \u23ed {skipped} skipped (already downloaded)", fg="yellow", bold=True))
        for r in results:
            if r["status"] != DOWNLOAD_SKIPPED:
                continue
            click.echo(click.style("  [skip] ", fg="yellow") + click.style(_trunc(r["url"], 70), fg="bright_black"))
            if r.get("title"):
                click.echo(click.style("         title  \u2192 ", fg="bright_black") + _trunc(r["title"], 60))
            click.echo(click.style("         folder \u2192 ", fg="bright_black") + click.style(_short_folder(r["folder"]), fg="cyan"))


# ---------------------------------------------------------------------------
# History display
# ---------------------------------------------------------------------------

def _show_history(*, full: bool = False, do_update: bool = False) -> None:
    if do_update:
        _run_history_update()

    records = load_all()
    click.echo(click.style("  History file \u2192 ", fg="bright_black") + click.style(str(HISTORY_FILE), fg="cyan"))
    click.echo("")

    if not records:
        click.echo(click.style("  No downloads recorded yet.", fg="bright_black"))
        return

    _W_IDX = 4; _W_DATE = 21; _W_TITLE = 55; _W_FMT = 5
    click.echo(
        click.style(f"  {'#':<{_W_IDX}}", fg="bright_black")
        + click.style(f"  {'Date (UTC)':<{_W_DATE}}", fg="bright_black")
        + click.style(f"  {'Title':<{_W_TITLE}}", fg="bright_black")
        + click.style(f"  {'Fmt':<{_W_FMT}}", fg="bright_black")
        + click.style("  Folder", fg="bright_black")
    )
    _rule(115)

    for i, rec in enumerate(records, 1):
        title  = rec.get("title") or "\u2014"
        folder = rec["folder"]
        folder_display = folder if full else _short_folder(folder, n=2)
        click.echo(
            click.style(f"  {i:<{_W_IDX}}", fg="bright_black")
            + click.style(f"  {rec['downloaded_at']:<{_W_DATE}}", fg="white")
            + f"  {_trunc(title, _W_TITLE):<{_W_TITLE}}"
            + click.style(f"  {rec['fmt'].upper():<{_W_FMT}}", fg="green")
            + "  " + click.style(folder_display, fg="cyan")
        )

    tip = "  (use --full to expand folder paths)" if not full else ""
    click.echo("")
    click.echo(click.style(f"  {len(records)} total record(s)", fg="bright_black") + click.style(tip, fg="bright_black"))


def _run_history_update() -> None:
    import yt_dlp as _ydl
    records = load_all()
    missing = [r for r in records if not r.get("title")]
    if not missing:
        click.echo(click.style("  All records already have titles.\n", fg="green"))
        return
    click.echo(click.style(f"  Fetching titles for {len(missing)} record(s)\u2026\n", fg="yellow"))
    with _ydl.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        for rec in missing:
            try:
                info  = ydl.extract_info(rec["url"], download=False)
                title = ""
                if isinstance(info, dict):
                    title = info.get("title", "") if "entries" not in info else (
                        (next(iter(info.get("entries") or []), None) or {}).get("title", ""))
                if title:
                    update_title(rec["url"], rec["config_key"], title)
                    click.echo(click.style("  \u2713 ", fg="green") + _trunc(title, 60))
            except Exception:  # noqa: BLE001
                click.echo(click.style("  \u2717 ", fg="red") + _trunc(rec["url"], 60))
    click.echo("")


def _do_install_ffmpeg() -> None:
    dest_dir = Path.home() / "sodo" / "bin"
    click.echo(click.style("  Installing FFmpeg to ~/sodo/bin...", fg="cyan"))
    from .downloader import download_ffmpeg
    success = download_ffmpeg(dest_dir)
    if success:
        click.echo(click.style("  ✓ Installation complete.", fg="green"))
    else:
        click.echo(click.style("  ✗ Installation failed.", fg="red"))
        sys.exit(1)


def _do_uninstall_ffmpeg() -> None:
    dest_dir = Path.home() / "sodo" / "bin"
    click.echo(click.style("  Uninstalling FFmpeg from ~/sodo/bin...", fg="cyan"))
    import shutil
    if dest_dir.exists():
        try:
            shutil.rmtree(dest_dir)
            click.echo(click.style("  ✓ Successfully uninstalled FFmpeg.", fg="green"))
        except Exception as e:
            click.echo(click.style(f"  ✗ Failed to uninstall FFmpeg: {e}", fg="red"))
            sys.exit(1)
    else:
        click.echo(click.style("  ▲ FFmpeg directory not found (nothing to uninstall).", fg="yellow"))


def _ensure_ffmpeg() -> None:
    from .downloader import is_ffmpeg_available, download_ffmpeg
    if not is_ffmpeg_available():
        if sys.stdin.isatty():
            click.echo("")
            if click.confirm(click.style("  [!] FFmpeg is required but was not found. Would you like to download it now to ~/sodo/bin?", fg="yellow"), default=True):
                dest_dir = Path.home() / "sodo" / "bin"
                if not download_ffmpeg(dest_dir):
                    click.echo(click.style("  ✗ Could not download FFmpeg. Exiting.", fg="red"))
                    sys.exit(1)
            else:
                click.echo(click.style("  ✗ FFmpeg is required. Exiting.", fg="red"))
                sys.exit(1)
        else:
            click.echo(click.style("  ✗ FFmpeg is required but not found in PATH or ~/sodo/bin. Run 'sodo --install' to download it.", fg="red"))
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------

@click.command("sodo", context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="sodo")
# ── history flags ──────────────────────────────────────────────────────────
@click.option("--history",    is_flag=True, default=False, help="Show download history.")
@click.option("--full",       is_flag=True, default=False, help="With --history: expand full folder paths.")
@click.option("--update",     "do_update",  is_flag=True, default=False, help="With --history: fetch missing titles.")
# ── summary ────────────────────────────────────────────────────────────────
@click.option("--summary",    is_flag=True, default=False, help="Show download statistics & admin info.")
@click.option("--cluster",    is_flag=True, default=False, help="Find and cluster similarly named downloads.")
# ── fail / retry ───────────────────────────────────────────────────────────
@click.option("--fails",      is_flag=True, default=False, help="List failed downloads.")
@click.option("--clear",      is_flag=True, default=False, help="Used with --fails to clear failed downloads.")
@click.option("--retry",      "retry_n",    is_flag=False, flag_value=0, default=None, type=int,
              metavar="N", help="Retry failed downloads. --retry=all, --retry N=top N.")
# ── log ────────────────────────────────────────────────────────────────────
@click.option("--log",        "show_log",   is_flag=False, flag_value=0, default=None, type=int,
              metavar="N", help="Show download log. --log=all, --log N=last N entries.")
@click.option("--missing",    is_flag=True, default=False, help="List all missing files and their URLs.")
# ── queue ──────────────────────────────────────────────────────────────────
@click.option("--add",        "add_urls",   multiple=True, metavar="URL",
              help="Add URL(s) to the download queue.")
@click.option("--queue",      "show_queue", is_flag=False, flag_value=0, default=None, type=int,
              metavar="N", help="Show queue. --queue=all, --queue N=top N.")
@click.option("--run",        "run_queue",  is_flag=True, default=False, help="Download everything in the queue.")
# ── todo ───────────────────────────────────────────────────────────────────
@click.option("--todo",       "todo_note",  default=None, metavar="NOTE",
              help="Add a todo note.")
@click.option("--todos",      is_flag=True, default=False, help="List all todo notes.")
@click.option("--todo-clear", "todo_clear_n", is_flag=False, flag_value=0, default=None, type=int,
              metavar="N", help="Clear todos. --todo-clear=all, --todo-clear N=top N.")
@click.option("--todo-drop",  "todo_drop_idx", multiple=True, type=int, metavar="IDX",
              help="Drop todos by index: --todo-drop 1 3 5")
# ── binaries ────────────────────────────────────────────────────────────────
@click.option("--install",    "install_bin", is_flag=True, default=False, help="Download and install FFmpeg to ~/sodo/bin.")
@click.option("--uninstall",  "uninstall_bin", is_flag=True, default=False, help="Uninstall/remove FFmpeg from ~/sodo/bin.")
# ── workspace ──────────────────────────────────────────────────────────────
@click.option("--init",       "init_ws",    is_flag=True, default=False, help="Initialize a .sodo workspace here.")
@click.option("--search",     "search_q",   default=None, metavar="QUERY", help="Fuzzy search. Default: local workspace.")
@click.option("-g", "--global", "is_global", is_flag=True, default=False, help="Perform action on the global log/queue/history.")
@click.option("--sync",       "sync_ws",    is_flag=True, default=False, help="Find moved files and repair registry.")
# ── download options ───────────────────────────────────────────────────────
@click.option("-m", "--music", is_flag=True, default=False, help="Download as MP3 (default, same as no flag).")
@click.option("--skip",       is_flag=True, default=False, help="Skip workspace requirement and download globally.")
@click.option("-f", "--force", is_flag=True, default=False, help="Force redownload even if globally downloaded.")
@click.option("--links",      is_flag=True, default=False, help="Print all downloaded URLs separated by spaces.")
@click.option(
    "--fmt",
    default=DEFAULT_FMT,
    type=click.Choice(list(FORMATS.keys()), case_sensitive=False),
    metavar="FORMAT",
    help=f"Output format. Choices: {', '.join(FORMATS)}. Default: {DEFAULT_FMT}.",
)
@click.option(
    "--pick", is_flag=True, default=False,
    help="Show an interactive format picker before downloading.",
)
@click.option("-o", "--output", type=click.Path(file_okay=False, writable=True),
              default=None, metavar="DIR", help="Output directory (default: cwd).")
@click.option("-q", "--quiet", is_flag=True, default=False, help="Suppress yt-dlp output.")
@click.argument("urls", nargs=-1, required=False, metavar="URL [URL ...]")
def main(
    urls: tuple[str, ...],
    music: bool,
    fmt: str,
    pick: bool,
    output: str | None,
    quiet: bool,
    # download options
    force: bool,
    links: bool,
    # history
    history: bool,
    full: bool,
    do_update: bool,
    # summary
    summary: bool,
    cluster: bool,
    # fails/retry
    fails: bool,
    clear: bool,
    retry_n: int | None,
    # log
    show_log: int | None,
    missing: bool,
    # queue
    add_urls: tuple[str, ...],
    show_queue: int | None,
    run_queue: bool,
    # todo
    todo_note: str | None,
    todos: bool,
    todo_clear_n: int | None,
    todo_drop_idx: tuple[int, ...],
    # workspace
    init_ws: bool,
    search_q: str | None,
    is_global: bool,
    sync_ws: bool,
    skip: bool,
    # binaries
    install_bin: bool,
    uninstall_bin: bool,
) -> None:
    """
    Download YouTube audio as MP3.

    \b
    IMPORTANT — always quote URLs in PowerShell:
      sodo "https://youtube.com/watch?v=XYZ&list=ABC"

    \b
    Quick reference
    ---------------
      sodo "URL"                  download
      sodo --history              show history  (--full for full paths, --update to fetch titles)
      sodo --init                 initialize a multimedia workspace in current folder
      sodo --search "term"        fuzzy search the local workspace
      sodo --search "term" -g     fuzzy search the global log
      sodo --sync                 repair broken paths (updates workspace AND global log)
      sodo --summary              stats & admin info
      sodo --log                  full download log (all attempts)
      sodo --log --update         repair missing file paths in global log
      sodo --missing              list globally missing files and their URLs
      sodo --fails                list failed downloads
      sodo --retry                retry all fails   (--retry 3  = top 3)
      sodo --add "URL1" "URL2"    add to queue
      sodo --queue                show queue        (--queue 5  = top 5)
      sodo --run                  download queue
      sodo --todo "note"          add a todo note
      sodo --todos                list todos
      sodo --todo-clear           clear all todos   (--todo-clear 2 = top 2)
      sodo --todo-drop 1 3        drop todos by index
    """
    if not links:
        _banner()
    out_dir = Path(output).expanduser().resolve() if output else Path.cwd()

    # ── install / uninstall FFmpeg ──────────────────────────────────────────
    if install_bin:
        _do_install_ffmpeg()
        return

    if uninstall_bin:
        _do_uninstall_ffmpeg()
        return

    # ── context override ────────────────────────────────────────────────────
    from . import store
    from . import history as hist_mod
    ws = find_workspace(out_dir)
    
    if not init_ws and not skip and not is_global:
        if not ws:
            click.echo(click.style("  \u2717 Not inside a .sodo workspace.", fg="red"))
            click.echo(click.style("  Run 'sodo --init' first, or use '--global' / '--skip'.", fg="bright_black"))
            sys.exit(1)
            
        local_dir = ws / ".sodo"
        hist_mod.SODO_DIR = local_dir
        hist_mod.HISTORY_FILE = local_dir / "history.json"
        
        store.SODO_DIR = local_dir
        store.LOG_FILE = local_dir / "log.json"
        store.QUEUE_FILE = local_dir / "queue.json"
        store.TODO_FILE = local_dir / "todo.json"

    # ── workspace ───────────────────────────────────────────────────────────
    if init_ws:
        _do_init(out_dir)
        return
        
    if search_q is not None:
        _do_search(search_q, out_dir, is_global)
        return
        
    if sync_ws:
        _do_sync(out_dir)
        return

    # ── history ─────────────────────────────────────────────────────────────
    # --update is context-sensitive: with --log it repairs the log;
    # with --history (or alone) it fetches missing titles from YouTube.
    if history or (do_update and show_log is None):
        _show_history(full=full, do_update=do_update)
        return

    # ── summary ─────────────────────────────────────────────────────────────
    if summary:
        _do_summary()
        return

    # ── cluster ─────────────────────────────────────────────────────────────
    if cluster:
        _do_cluster(is_global)
        return

    # ── fail ────────────────────────────────────────────────────────────────
    if fails:
        if clear:
            _do_fails_clear(out_dir, skip)
            return
        _do_fails()
        return

    # ── retry ───────────────────────────────────────────────────────────────
    if retry_n is not None:
        _do_retry(retry_n, out_dir, quiet, skip, force)
        return

    # ── log ─────────────────────────────────────────────────────────────────
    if show_log is not None:
        if do_update:
            _do_log_update()
        _do_log(show_log or None)
        return

    # ── missing ─────────────────────────────────────────────────────────────
    if missing:
        _do_missing()
        return

    # ── links ───────────────────────────────────────────────────────────────
    if links:
        _do_links(out_dir, is_global)
        return

    # ── queue: add ──────────────────────────────────────────────────────────
    if add_urls:
        _do_add(add_urls)
        return

    # ── queue: show ─────────────────────────────────────────────────────────
    if show_queue is not None:
        _do_queue(show_queue or None, full)
        return

    # ── queue: run ──────────────────────────────────────────────────────────
    if run_queue:
        _do_run(out_dir, quiet, skip, force)
        return

    # ── todo: add ───────────────────────────────────────────────────────────
    if todo_note is not None:
        idx = todo_add(todo_note)
        click.echo(click.style(f'  \u2713 Added todo #{idx}: ', fg="green") + f'"{todo_note}"')
        click.echo("")
        return

    # ── todo: list ──────────────────────────────────────────────────────────
    if todos:
        _do_todos(full)
        return

    # ── todo: clear ─────────────────────────────────────────────────────────
    if todo_clear_n is not None:
        removed = todo_clear(todo_clear_n or None)
        click.echo(click.style(f"  \u2713 Cleared {removed} todo(s).", fg="green"))
        click.echo("")
        return

    # ── todo: drop ──────────────────────────────────────────────────────────
    if todo_drop_idx:
        removed = todo_drop(list(todo_drop_idx))
        click.echo(click.style(f"  \u2713 Dropped {removed} todo(s).", fg="green"))
        click.echo("")
        return

    # ── normal download ─────────────────────────────────────────────────────
    if not urls:
        raise click.UsageError(
            "Missing URL argument. Run 'sodo -h' for help."
        )

    ws = find_workspace(out_dir)
    if not ws and not skip:
        click.echo(click.style("  \u2717 Not inside a .sodo workspace.", fg="red"))
        click.echo(click.style("  Run 'sodo --init' first to create a workspace here,", fg="bright_black"))
        click.echo(click.style("  Or use 'sodo \"URL\" --skip' to download globally without a workspace.", fg="bright_black"))
        sys.exit(1)
        
    ws_str = "untracked" if skip else str(ws)

    _check_urls(urls)

    _ensure_ffmpeg()

    # Format selection: --pick > --fmt > default mp3
    chosen_fmt = DEFAULT_FMT
    if pick:
        chosen_fmt = _pick_format()
    elif fmt != DEFAULT_FMT:
        chosen_fmt = fmt

    config_key = make_config_key(fmt=chosen_fmt, output_dir=out_dir)
    click.echo("  Output \u2192 " + click.style(str(out_dir), fg="cyan"))
    click.echo(
        "  Format \u2192 "
        + click.style(FORMATS[chosen_fmt]["label"], fg="green", bold=True)
        + click.style(f"  ({FORMATS[chosen_fmt]['desc']})", fg="bright_black")
    )
    click.echo(f"  URLs   \u2192 {len(urls)}")
    if skip:
        click.echo(click.style("  Mode   \u2192 Global (--skip)", fg="yellow"))
    else:
        click.echo(click.style(f"  Space  \u2192 {ws}", fg="cyan"))
    click.echo("")

    start   = time.perf_counter()
    results = download_audio(list(urls), out_dir, fmt=chosen_fmt, quiet=quiet, config_key=config_key, force=force)
    elapsed = time.perf_counter() - start

    _dual_write_results(results, ws, skip, config_key, out_dir, ws_str)

    _print_summary(results)
    click.echo(click.style(f"  Time   \u2192 {elapsed:.1f}s", fg="bright_black"))

    if any(r["status"] == DOWNLOAD_FAIL for r in results):
        sys.exit(1)

