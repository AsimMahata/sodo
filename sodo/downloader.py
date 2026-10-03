"""Core download logic for sodo."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import yt_dlp

from .history import HistoryEntry, record_download, was_downloaded
from .progress import SodoPostprocessorHook, SodoProgressHook

# ---------------------------------------------------------------------------
# Bundled FFmpeg
# ---------------------------------------------------------------------------

_BIN_DIR = Path.home() / "sodo" / "bin"


def _ffmpeg_dir() -> str | None:
    """Return the ffmpeg directory path (prioritizing tools/sodo/bin, ~/tools/sodo/bin, package bin), or None."""
    exe_suffix = ".exe" if sys.platform == "win32" else ""

    candidates = [
        # 1. Root of sodo repo (e.g. tools/sodo/bin)
        Path(__file__).resolve().parent.parent / "bin",
        # 2. ~/tools/sodo/bin
        Path.home() / "tools" / "sodo" / "bin",
        # 3. ~/projects/tools/sodo/bin
        Path.home() / "projects" / "tools" / "sodo" / "bin",
        # 4. ~/sodo/bin
        _BIN_DIR,
        # 5. sodo/sodo/bin (package level)
        Path(__file__).parent / "bin",
    ]

    for candidate in candidates:
        ffmpeg_file = candidate / f"ffmpeg{exe_suffix}"
        ffprobe_file = candidate / f"ffprobe{exe_suffix}"
        if ffmpeg_file.is_file() and ffprobe_file.is_file():
            return str(candidate)

    return None


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available locally or in the system PATH."""
    import shutil
    if _ffmpeg_dir() is not None:
        return True
    return shutil.which("ffmpeg") is not None


def download_ffmpeg(dest_dir: Path) -> bool:
    """Download and extract FFmpeg/FFprobe binaries to dest_dir."""
    import shutil
    import urllib.request
    import zipfile
    import click

    dest_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        click.echo(click.style("\n[!] Automatic download is only supported on Windows.", fg="yellow"))
        if sys.platform == "darwin":
            click.echo("    Please install FFmpeg via Homebrew: brew install ffmpeg")
        else:
            click.echo("    Please install FFmpeg via your package manager (e.g. sudo apt install ffmpeg)")
        return False

    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    temp_zip = dest_dir / "ffmpeg_temp.zip"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        click.echo(f"Connecting to {url}...")
        with urllib.request.urlopen(req) as response:
            total_size = int(response.info().get("Content-Length", 0))
            block_size = 1024 * 1024  # 1MB chunks

            with click.progressbar(length=total_size, label="  Downloading FFmpeg") as bar:
                with open(temp_zip, "wb") as f:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        f.write(buffer)
                        bar.update(len(buffer))

        click.echo("  Extracting binaries...")
        with zipfile.ZipFile(temp_zip) as z:
            for member in z.infolist():
                filename = Path(member.filename)
                if filename.name in ("ffmpeg.exe", "ffprobe.exe"):
                    with z.open(member) as source, open(dest_dir / filename.name, "wb") as target:
                        shutil.copyfileobj(source, target)

        click.echo(click.style(f"  ✓ FFmpeg successfully installed to {dest_dir}", fg="green"))
        return True
    except Exception as e:
        click.echo(click.style(f"  ✗ Failed to download FFmpeg: {e}", fg="red"))
        return False
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
_TRAILING = re.compile(r"[\s.]+$")


def sanitize_filename(name: str) -> str:
    """Remove / replace characters that are illegal on Windows / POSIX."""
    name = _INVALID_CHARS.sub("_", name)
    name = _TRAILING.sub("", name)
    return name[:200] or "media"


_YT_KEEP_PARAMS = {"v", "t"}
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}


def is_playlist_url(url: str, *, playlist_mode: bool | None = None) -> bool:
    """Return True if url represents or contains a playlist to download."""
    if playlist_mode is False:
        return False
    if playlist_mode is True:
        return True

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    host = parsed.netloc.lower().lstrip("www.")

    # Dedicated YouTube playlist endpoint
    if host in _YT_HOSTS and parsed.path.startswith("/playlist"):
        return True

    # YouTube watch or short link with playlist parameter
    if host in _YT_HOSTS or host in ("youtu.be", "www.youtu.be"):
        qs = parse_qs(parsed.query)
        list_param = qs.get("list", [""])[0]
        if list_param:
            # Algorithmic radio mixes (RD...) are auto-generated dynamic queues.
            # Real playlists (PL, UU, FL, LP, OLAK5uy_, etc.) are treated as playlists.
            if not list_param.startswith("RD"):
                return True

    # Other platform playlists / albums
    if "/sets/" in parsed.path or "/album/" in parsed.path:
        return True

    return False


def clean_url(url: str, *, allow_playlist: bool = True, force_playlist: bool = False) -> str:
    """Clean and normalize a media URL, preserving or converting playlist URLs when appropriate."""
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    host = parsed.netloc.lower().lstrip("www.")

    # youtu.be short links
    if host in ("youtu.be", "www.youtu.be"):
        qs = parse_qs(parsed.query, keep_blank_values=False)
        list_param = qs.get("list", [""])[0]
        if (allow_playlist or force_playlist) and list_param and (force_playlist or not list_param.startswith("RD")):
            return f"https://www.youtube.com/playlist?list={list_param}"
        return urlunparse(parsed._replace(query="", fragment=""))

    # Full YouTube URLs
    if host in _YT_HOSTS:
        qs = parse_qs(parsed.query, keep_blank_values=False)
        list_param = qs.get("list", [""])[0]

        # Dedicated playlist endpoint
        if parsed.path.startswith("/playlist"):
            if list_param:
                return f"https://www.youtube.com/playlist?list={list_param}"
            return url

        # Watch URL: https://www.youtube.com/watch?v=...&list=...
        if parsed.path == "/watch":
            if (allow_playlist or force_playlist) and list_param and (force_playlist or not list_param.startswith("RD")):
                return f"https://www.youtube.com/playlist?list={list_param}"

            kept = {k: v for k, v in qs.items() if k in _YT_KEEP_PARAMS}
            new_query = urlencode({k: v[0] for k, v in kept.items()})
            return urlunparse(parsed._replace(query=new_query, fragment=""))

    return url


# ---------------------------------------------------------------------------
# Format catalogue
# ---------------------------------------------------------------------------

FORMATS: dict[str, dict] = {
    "mp3":  {"label": "MP3",  "type": "audio", "desc": "best quality VBR (default)"},
    "flac": {"label": "FLAC", "type": "audio", "desc": "lossless"},
    "wav":  {"label": "WAV",  "type": "audio", "desc": "lossless PCM"},
    "m4a":  {"label": "M4A",  "type": "audio", "desc": "AAC audio"},
    "opus": {"label": "OPUS", "type": "audio", "desc": "efficient / small size"},
    "mp4":  {"label": "MP4",  "type": "video", "desc": "video + audio"},
    "webm": {"label": "WEBM", "type": "video", "desc": "video + audio (no re-encode)"},
}

DEFAULT_FMT = "mp3"


def build_opts_for_format(
    fmt: str,
    output_dir: Path,
    *,
    quiet: bool = False,
    track_num: int | None = None,
    total_tracks: int | None = None,
    playlist_title: str = "",
) -> dict[str, Any]:
    """Return yt-dlp options dict for the requested format."""
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(FORMATS)}")

    outtmpl = str(output_dir / "%(title)s.%(ext)s")

    progress_hook = SodoProgressHook(
        track_num=track_num,
        total_tracks=total_tracks,
        playlist_title=playlist_title,
        quiet=quiet,
    )
    postprocessor_hook = SodoPostprocessorHook(fmt=fmt, quiet=quiet)

    base: dict[str, Any] = {
        "outtmpl":              outtmpl,
        "restrictfilenames":    False,
        "windowsfilenames":     True,
        "progress_hooks":       [progress_hook],
        "postprocessor_hooks":  [postprocessor_hook],
        "quiet":                True,
        "no_warnings":          quiet,
        "keepvideo":            False,
        "ignoreerrors":         True,
        "js_runtimes": {
            "node": {},
            "deno": {},
            "quickjs": {},
        },
    }

    ffmpeg_dir = _ffmpeg_dir()
    if ffmpeg_dir:
        base["ffmpeg_location"] = ffmpeg_dir

    if FORMATS[fmt]["type"] == "audio":
        base["format"] = "bestaudio/best"
        base["addmetadata"] = True
        base["writethumbnail"] = True
        base["embedthumbnail"] = True
        base["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                "preferredquality": "0" if fmt == "mp3" else "",
            },
            {"key": "EmbedThumbnail"},
            {"key": "FFmpegMetadata", "add_metadata": True},
        ]
    else:
        # video formats (MP4, WEBM)
        base["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        base["addmetadata"] = True
        base["merge_output_format"] = fmt
        base["postprocessors"] = [
            {"key": "FFmpegMetadata", "add_metadata": True},
        ]

    return base


def build_mp3_opts(urls: list[str], output_dir: Path, *, quiet: bool = False) -> dict[str, Any]:
    return build_opts_for_format("mp3", output_dir, quiet=quiet)


# Status sentinels
DOWNLOAD_OK      = "ok"
DOWNLOAD_FAIL    = "fail"
DOWNLOAD_SKIPPED = "skipped"


def _extract_title(info: object) -> str:
    """Pull the title out of a yt-dlp info dict."""
    if not isinstance(info, dict):
        return ""
    if "entries" in info:
        first = next(iter(info.get("entries") or []), None)
        return first.get("title", "") if isinstance(first, dict) else ""
    return info.get("title", "")


def _extract_filepath(info: object) -> str:
    """Extract the final saved file path from a yt-dlp info dict."""
    if not isinstance(info, dict):
        return ""
    requested = info.get("requested_downloads")
    if isinstance(requested, list) and requested:
        for key in ("filepath", "filename"):
            fp = requested[0].get(key, "")
            if fp:
                return str(fp)
    for key in ("filepath", "filename", "_filename"):
        fp = info.get(key, "")
        if fp:
            return str(fp)
    return ""


# ---------------------------------------------------------------------------
# Playlist Downloader
# ---------------------------------------------------------------------------

def _download_playlist(
    url: str,
    output_dir: Path,
    *,
    fmt: str = DEFAULT_FMT,
    quiet: bool = False,
    config_key: str = "",
    force: bool = False,
) -> list[dict]:
    """Download an entire playlist track by track with rich progress UI and global deduplication."""
    folder_str = str(output_dir.resolve())
    results: list[dict] = []

    flat_opts: dict[str, Any] = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"node": {}, "deno": {}, "quickjs": {}},
    }
    ffmpeg_dir = _ffmpeg_dir()
    if ffmpeg_dir:
        flat_opts["ffmpeg_location"] = ffmpeg_dir

    if not quiet:
        print("[sodo] ⏳ Fetching playlist information...")

    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as exc:
            err = str(exc)
            print(f"\n[sodo] ✗ Could not load playlist {url}: {err}", file=sys.stderr)
            return [{
                "url": url, "cleaned": url,
                "status": DOWNLOAD_FAIL,
                "title": "Playlist",
                "filepath": "",
                "error": err,
                "folder": folder_str,
                "skipped_entry": None,
            }]

    if not info:
        return []

    raw_entries = info.get("entries")
    if raw_entries is None:
        single_opts = build_opts_for_format(fmt, output_dir, quiet=quiet)
        with yt_dlp.YoutubeDL(single_opts) as ydl:
            try:
                single_info = ydl.extract_info(url, download=True)
                title = _extract_title(single_info)
                filepath = _extract_filepath(single_info)
                if config_key:
                    record_download(url, config_key, output_dir, title=title)
                return [{
                    "url": url, "cleaned": url,
                    "status": DOWNLOAD_OK,
                    "title": title,
                    "filepath": filepath,
                    "error": "", "folder": folder_str,
                    "skipped_entry": None,
                }]
            except Exception as exc:
                return [{
                    "url": url, "cleaned": url,
                    "status": DOWNLOAD_FAIL,
                    "title": "", "filepath": "",
                    "error": str(exc), "folder": folder_str,
                    "skipped_entry": None,
                }]

    entries = [e for e in raw_entries if e and isinstance(e, dict)]
    total = len(entries)
    playlist_title = info.get("title") or "YouTube Playlist"
    uploader = info.get("uploader") or info.get("channel") or info.get("uploader_id") or ""
    fmt_label = FORMATS.get(fmt, {}).get("label", fmt.upper())
    fmt_desc  = FORMATS.get(fmt, {}).get("desc", "")

    if not quiet:
        print("")
        print("  " + "═" * 70)
        print(f"  📋 Playlist : {playlist_title}")
        if uploader:
            print(f"  👤 Channel  : {uploader}")
        print(f"  🔢 Total    : {total} track{'s' if total != 1 else ''}")
        print(f"  📁 Output   : {output_dir}")
        print(f"  🎬 Format   : {fmt_label}  ({fmt_desc})")
        print("  " + "═" * 70)
        print("")

    for idx, entry in enumerate(entries, 1):
        track_id = entry.get("id") or ""
        track_title = entry.get("title") or f"Track {idx}"
        track_url = entry.get("url") or (f"https://www.youtube.com/watch?v={track_id}" if track_id else "")
        if not track_url.startswith(("http://", "https://")):
            track_url = f"https://www.youtube.com/watch?v={track_id or entry.get('url')}"

        # Global history deduplication
        if config_key and not force:
            from .history import was_downloaded_globally
            skipped_entry = was_downloaded_globally(track_url, config_key)
            if skipped_entry is not None:
                if not quiet:
                    dest = skipped_entry.get("folder", "unknown")
                    print(f"  ⏭  [{idx}/{total}] Skipped: {track_title[:55]} (already at {dest})")
                results.append({
                    "url": track_url,
                    "cleaned": track_url,
                    "status": DOWNLOAD_SKIPPED,
                    "title": skipped_entry.get("title") or track_title,
                    "filepath": "",
                    "error": "",
                    "folder": skipped_entry.get("folder", folder_str),
                    "skipped_entry": skipped_entry,
                    "playlist": playlist_title,
                })
                continue

        track_opts = build_opts_for_format(
            fmt,
            output_dir,
            quiet=quiet,
            track_num=idx,
            total_tracks=total,
            playlist_title=playlist_title,
        )
        track_opts["noplaylist"] = True

        with yt_dlp.YoutubeDL(track_opts) as ydl:
            try:
                t_info = ydl.extract_info(track_url, download=True)
                final_title = _extract_title(t_info) or track_title
                final_path = _extract_filepath(t_info)
                if config_key:
                    record_download(track_url, config_key, output_dir, title=final_title)
                if not quiet:
                    size_mb = ""
                    if final_path and Path(final_path).exists():
                        size_mb = f" ({Path(final_path).stat().st_size / 1_048_576:.1f} MB)"
                    print(f"  ✓ [{idx}/{total}] {final_title}{size_mb} • {fmt_label}")
                results.append({
                    "url": track_url,
                    "cleaned": track_url,
                    "status": DOWNLOAD_OK,
                    "title": final_title,
                    "filepath": final_path,
                    "error": "",
                    "folder": folder_str,
                    "skipped_entry": None,
                    "playlist": playlist_title,
                })
            except yt_dlp.utils.DownloadError as exc:
                err = str(exc)
                if not quiet:
                    print(f"\n  ✗ [{idx}/{total}] Failed: {track_title}\n       {err}", file=sys.stderr)
                results.append({
                    "url": track_url,
                    "cleaned": track_url,
                    "status": DOWNLOAD_FAIL,
                    "title": track_title,
                    "filepath": "",
                    "error": err,
                    "folder": folder_str,
                    "skipped_entry": None,
                    "playlist": playlist_title,
                })
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
                if not quiet:
                    print(f"\n  ✗ [{idx}/{total}] Unexpected error: {track_title}\n       {err}", file=sys.stderr)
                results.append({
                    "url": track_url,
                    "cleaned": track_url,
                    "status": DOWNLOAD_FAIL,
                    "title": track_title,
                    "filepath": "",
                    "error": err,
                    "folder": folder_str,
                    "skipped_entry": None,
                    "playlist": playlist_title,
                })

    return results


# ---------------------------------------------------------------------------
# Public Download Function
# ---------------------------------------------------------------------------

def download_audio(
    urls: list[str],
    output_dir: Path,
    *,
    fmt: str = DEFAULT_FMT,
    quiet: bool = False,
    config_key: str = "",
    force: bool = False,
    playlist_mode: bool | None = None,
) -> list[dict]:
    """Download audio or video from *urls*, supporting playlists and individual tracks."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    folder_str = str(output_dir.resolve())

    for url in urls:
        is_pl = is_playlist_url(url, playlist_mode=playlist_mode)
        cleaned = clean_url(
            url,
            allow_playlist=(playlist_mode is not False),
            force_playlist=(playlist_mode is True),
        )
        if cleaned != url and not quiet:
            print(f"[sodo] cleaned URL: {cleaned}")

        if is_pl:
            pl_results = _download_playlist(
                cleaned,
                output_dir,
                fmt=fmt,
                quiet=quiet,
                config_key=config_key,
                force=force,
            )
            results.extend(pl_results)
            continue

        # Single track download
        if config_key and not force:
            from .history import was_downloaded_globally
            entry = was_downloaded_globally(cleaned, config_key)
            if entry is not None:
                if not quiet:
                    print(f"[sodo] ⏭  Skipped: {cleaned} (Globally available at {entry.get('folder', 'unknown')})")
                results.append({
                    "url": url, "cleaned": cleaned,
                    "status": DOWNLOAD_SKIPPED,
                    "title": entry.get("title", ""),
                    "filepath": "",
                    "error": "", "folder": entry.get("folder", ""),
                    "skipped_entry": entry,
                })
                continue

        opts = build_opts_for_format(fmt, output_dir, quiet=quiet)
        opts["noplaylist"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(cleaned, download=True)
                title = _extract_title(info)
                filepath = _extract_filepath(info)
                if config_key:
                    record_download(cleaned, config_key, output_dir, title=title)
                if not quiet:
                    size_mb = ""
                    if filepath and Path(filepath).exists():
                        size_mb = f" ({Path(filepath).stat().st_size / 1_048_576:.1f} MB)"
                    fmt_label = FORMATS.get(fmt, {}).get("label", fmt.upper())
                    print(f"  ✓ {title}{size_mb} • {fmt_label}")
                results.append({
                    "url": url, "cleaned": cleaned,
                    "status": DOWNLOAD_OK,
                    "title": title,
                    "filepath": filepath,
                    "error": "", "folder": folder_str,
                    "skipped_entry": None,
                })
            except yt_dlp.utils.DownloadError as exc:
                err = str(exc)
                print(f"\n[sodo] ✗ Failed: {cleaned}\n       {err}", file=sys.stderr)
                results.append({
                    "url": url, "cleaned": cleaned,
                    "status": DOWNLOAD_FAIL,
                    "title": "", "filepath": "", "error": err, "folder": folder_str,
                    "skipped_entry": None,
                })
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
                print(f"\n[sodo] ✗ Unexpected error for {cleaned}: {err}", file=sys.stderr)
                results.append({
                    "url": url, "cleaned": cleaned,
                    "status": DOWNLOAD_FAIL,
                    "title": "", "filepath": "", "error": err, "folder": folder_str,
                    "skipped_entry": None,
                })

    return results
