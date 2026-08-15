"""Core download logic for sodo."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import yt_dlp

from .history import HistoryEntry, record_download, was_downloaded

# ---------------------------------------------------------------------------
# Bundled FFmpeg
# ---------------------------------------------------------------------------

# sodo ships ffmpeg.exe + ffprobe.exe in sodo/bin/  (Windows only).
# On other platforms the binaries won't exist and yt-dlp falls back to PATH.
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
    import urllib.request
    import zipfile
    import shutil
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
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        click.echo(f"Connecting to {url}...")
        with urllib.request.urlopen(req) as response:
            total_size = int(response.info().get('Content-Length', 0))
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
                    # Extract directly to dest_dir without parent folders
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

from .progress import SodoProgressHook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
_TRAILING = re.compile(r"[\s.]+$")


def sanitize_filename(name: str) -> str:
    """Remove / replace characters that are illegal on Windows / POSIX."""
    name = _INVALID_CHARS.sub("_", name)
    name = _TRAILING.sub("", name)
    return name[:200] or "audio"


# Keep only these query params for YouTube watch URLs — everything else
# (list, start_radio, index, pp, si, …) is playlist/session noise.
_YT_KEEP_PARAMS = {"v", "t"}
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}


def clean_url(url: str) -> str:
    """Strip playlist / radio cruft from a YouTube URL.

    Examples
    --------
    >>> clean_url("https://www.youtube.com/watch?v=abc123&list=RDabc123&start_radio=1")
    'https://www.youtube.com/watch?v=abc123'
    >>> clean_url("https://youtu.be/abc123?si=XYZ")
    'https://youtu.be/abc123'
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url  # not a parseable URL — leave as-is

    host = parsed.netloc.lower().lstrip("www.")

    # youtu.be short links — video ID is the path, query params are noise
    if host in ("youtu.be", "www.youtu.be"):
        return urlunparse(parsed._replace(query="", fragment=""))

    # Full YouTube watch URLs
    if host in _YT_HOSTS and parsed.path == "/watch":
        qs = parse_qs(parsed.query, keep_blank_values=False)
        kept = {k: v for k, v in qs.items() if k in _YT_KEEP_PARAMS}
        new_query = urlencode({k: v[0] for k, v in kept.items()})
        return urlunparse(parsed._replace(query=new_query, fragment=""))

    # Anything else — return unchanged
    return url


# ---------------------------------------------------------------------------
# MP3 download
# ---------------------------------------------------------------------------
# Format catalogue
# ---------------------------------------------------------------------------

# Each entry: label, type (audio|video), description, yt-dlp codec key
FORMATS: dict[str, dict] = {
    "mp3":  {"label": "MP3",  "type": "audio", "desc": "best quality VBR  (default)"},
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
) -> dict[str, Any]:
    """Return yt-dlp options dict for the requested format."""
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(FORMATS)}")

    outtmpl = str(output_dir / "%(title)s.%(ext)s")

    base: dict[str, Any] = {
        "outtmpl":          outtmpl,
        "restrictfilenames": False,
        "windowsfilenames":  True,
        "progress_hooks":   [SodoProgressHook()],
        "quiet":            quiet,
        "no_warnings":      quiet,
        "keepvideo":        False,
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
        # video formats
        base["format"] = "bestvideo+bestaudio/best"
        base["addmetadata"] = True
        base["merge_output_format"] = fmt
        base["postprocessors"] = [
            {"key": "FFmpegMetadata", "add_metadata": True},
        ]

    return base


# Keep old name as an alias so nothing else breaks
def build_mp3_opts(urls: list[str], output_dir: Path, *, quiet: bool = False) -> dict[str, Any]:
    return build_opts_for_format("mp3", output_dir, quiet=quiet)


# Status sentinels
DOWNLOAD_OK      = "ok"
DOWNLOAD_FAIL    = "fail"
DOWNLOAD_SKIPPED = "skipped"


def _extract_title(info: object) -> str:
    """Pull the video title out of a yt-dlp info dict (handles playlists)."""
    if not isinstance(info, dict):
        return ""
    if "entries" in info:
        first = next(iter(info.get("entries") or []), None)
        return first.get("title", "") if isinstance(first, dict) else ""
    return info.get("title", "")


def _extract_filepath(info: object) -> str:
    """Extract the final saved file path (with extension) from a yt-dlp info dict.

    After postprocessing (e.g. FFmpeg → MP3 conversion), yt-dlp stores the
    real output path in ``requested_downloads[0]['filepath']``.
    """
    if not isinstance(info, dict):
        return ""
    # Primary: postprocessed path lives here
    requested = info.get("requested_downloads")
    if isinstance(requested, list) and requested:
        for key in ("filepath", "filename"):
            fp = requested[0].get(key, "")
            if fp:
                return str(fp)
    # Fallback: top-level keys
    for key in ("filepath", "filename", "_filename"):
        fp = info.get(key, "")
        if fp:
            return str(fp)
    return ""


def download_audio(
    urls: list[str],
    output_dir: Path,
    *,
    fmt: str = DEFAULT_FMT,
    quiet: bool = False,
    config_key: str = "",
    force: bool = False,
) -> list[dict]:
    """
    Download audio/video from *urls*.

    Each URL is cleaned (playlist params stripped) before use.
    Returns a list of dicts: url, cleaned, status, title, error, folder, skipped_entry.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    folder_str = str(output_dir.resolve())
    opts = build_opts_for_format(fmt, output_dir, quiet=quiet)

    with yt_dlp.YoutubeDL(opts) as ydl:
        for url in urls:
            cleaned = clean_url(url)
            if cleaned != url and not quiet:
                print(f"[sodo] cleaned URL: {cleaned}")

            # --- history check -----------------------------------------------
            if config_key and not force:
                from .history import was_downloaded_globally
                # As per Phase 3, we ALWAYS check the global master index to prevent system-wide duplicates.
                entry = was_downloaded_globally(cleaned, config_key)
                if entry is not None:
                    if not quiet:
                        print(f"[sodo] \u23ed Skipped: {cleaned} (Globally available at {entry.get('folder', 'unknown')})")
                    results.append({
                        "url": url, "cleaned": cleaned,
                        "status": DOWNLOAD_SKIPPED,
                        "title": entry.get("title", ""),
                        "error": "", "folder": entry.get("folder", ""),
                        "skipped_entry": entry,
                    })
                    continue

            # --- actual download ---------------------------------------------
            try:
                info     = ydl.extract_info(cleaned, download=True)
                title    = _extract_title(info)
                filepath = _extract_filepath(info)
                if config_key:
                    record_download(cleaned, config_key, output_dir, title=title)
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
                print(f"\n[sodo] \u2717 Failed: {cleaned}\n       {err}", file=sys.stderr)
                results.append({
                    "url": url, "cleaned": cleaned,
                    "status": DOWNLOAD_FAIL,
                    "title": "", "error": err, "folder": folder_str,
                    "skipped_entry": None,
                })
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
                print(f"\n[sodo] \u2717 Unexpected error for {cleaned}: {err}", file=sys.stderr)
                results.append({
                    "url": url, "cleaned": cleaned,
                    "status": DOWNLOAD_FAIL,
                    "title": "", "error": err, "folder": folder_str,
                    "skipped_entry": None,
                })

    return results

