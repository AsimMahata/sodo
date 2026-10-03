"""Rich progress and postprocessor hooks for yt-dlp."""

from __future__ import annotations

import sys


class SodoProgressHook:
    """yt-dlp progress hook that renders a clean, modern terminal progress bar."""

    BAR_WIDTH = 26

    def __init__(
        self,
        *,
        track_num: int | None = None,
        total_tracks: int | None = None,
        playlist_title: str = "",
        quiet: bool = False,
    ) -> None:
        self.track_num = track_num
        self.total_tracks = total_tracks
        self.playlist_title = playlist_title
        self.quiet = quiet
        self._title: str = ""
        self._stream_type: str = ""
        self._last_line_len: int = 0

    # ------------------------------------------------------------------
    def __call__(self, d: dict) -> None:  # noqa: D401
        if self.quiet:
            return

        status = d.get("status")
        if status == "downloading":
            self._render_downloading(d)
        elif status == "finished":
            self._render_finished(d)
        elif status == "error":
            prefix = f"[{self.track_num}/{self.total_tracks}] " if self.track_num and self.total_tracks else ""
            print(f"\n  [sodo] ✗ {prefix}Download error", file=sys.stderr)

    # ------------------------------------------------------------------
    def _render_downloading(self, d: dict) -> None:
        info = d.get("info_dict", {})
        title = info.get("title", "") or "Media"

        # Detect stream type (e.g. video vs audio)
        vcodec = info.get("vcodec")
        acodec = info.get("acodec")
        resolution = info.get("resolution") or (
            f"{info.get('width')}x{info.get('height')}" if info.get("width") else ""
        )
        format_note = info.get("format_note", "")

        stream_tag = ""
        if vcodec and vcodec != "none":
            stream_tag = f"video {resolution or format_note}".strip()
        elif acodec and acodec != "none":
            stream_tag = f"audio {format_note}".strip() or "audio"

        # When starting a new track or switching streams (e.g. video -> audio stream)
        stream_id = f"{title}_{stream_tag}"
        if stream_id != self._stream_type:
            self._stream_type = stream_id
            prefix = f"[{self.track_num}/{self.total_tracks}] " if self.track_num and self.total_tracks else ""
            tag_str = f"  [{stream_tag}]" if stream_tag else ""
            title_display = title[:60] + ("…" if len(title) > 60 else "")
            # Clear previous bar if any
            sys.stdout.write("\r" + " " * max(self._last_line_len, 40) + "\r")
            print(f"  ↓ {prefix}{title_display}{tag_str}")

        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        downloaded = d.get("downloaded_bytes", 0)
        speed = d.get("speed") or 0
        eta = d.get("eta") or 0

        # Bar rendering
        if total:
            frac = min(downloaded / total, 1.0)
            filled = int(self.BAR_WIDTH * frac)
            bar = "█" * filled + "░" * (self.BAR_WIDTH - filled)
            pct = frac * 100
            size_mb = total / 1_048_576
            dl_mb = downloaded / 1_048_576
            speed_str = (
                f"{speed / 1_048_576:.1f} MB/s"
                if speed >= 1_048_576
                else f"{speed / 1024:.0f} KB/s"
            )
            eta_str = f"ETA {eta}s" if eta else "      "
            line = f"\r    [{bar}] {pct:5.1f}%  {dl_mb:5.1f}/{size_mb:5.1f} MB  {speed_str:<9} {eta_str}"
        else:
            dl_mb = downloaded / 1_048_576
            speed_str = (
                f"{speed / 1_048_576:.1f} MB/s"
                if speed >= 1_048_576
                else f"{speed / 1024:.0f} KB/s"
            )
            bar = "·" * self.BAR_WIDTH
            line = f"\r    [{bar}]  {dl_mb:5.1f} MB  {speed_str:<9}"

        self._last_line_len = len(line)
        sys.stdout.write(line)
        sys.stdout.flush()

    # ------------------------------------------------------------------
    def _render_finished(self, d: dict) -> None:
        total = d.get("total_bytes") or d.get("downloaded_bytes", 0)
        size_mb = total / 1_048_576 if total else 0.0
        bar = "█" * self.BAR_WIDTH
        line = f"\r    [{bar}] 100.0%  {size_mb:5.1f} MB  downloaded    "
        self._last_line_len = len(line)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


class SodoPostprocessorHook:
    """yt-dlp postprocessor hook to display clean conversion/merging status."""

    def __init__(self, fmt: str = "mp3", *, quiet: bool = False) -> None:
        self.fmt = fmt.upper()
        self.quiet = quiet
        self._last_len: int = 0

    def __call__(self, d: dict) -> None:
        if self.quiet:
            return

        status = d.get("status")
        pp = d.get("postprocessor", "")

        if status == "started":
            msg = ""
            if "Merger" in pp:
                msg = f"    ⚙ Merging video + audio into {self.fmt}..."
            elif "ExtractAudio" in pp:
                msg = f"    ⚙ Extracting audio to {self.fmt}..."
            elif "EmbedThumbnail" in pp:
                msg = "    🖼 Embedding artwork..."
            elif "Metadata" in pp:
                msg = "    🏷 Writing metadata tags..."

            if msg:
                sys.stdout.write(f"\r{msg}\r")
                sys.stdout.flush()
                self._last_len = max(self._last_len, len(msg))

        elif status == "finished":
            if self._last_len:
                sys.stdout.write("\r" + " " * (self._last_len + 5) + "\r")
                sys.stdout.flush()
                self._last_len = 0
