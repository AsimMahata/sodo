"""Rich progress hook for yt-dlp."""

from __future__ import annotations

import sys


class SodoProgressHook:
    """yt-dlp progress hook that renders a clean terminal progress bar."""

    BAR_WIDTH = 30

    def __init__(self) -> None:
        self._title: str = ""

    # ------------------------------------------------------------------
    def __call__(self, d: dict) -> None:  # noqa: D401
        status = d.get("status")

        if status == "downloading":
            self._render_downloading(d)
        elif status == "finished":
            self._render_finished(d)
        elif status == "error":
            print("\n[sodo] ✗ Download error", file=sys.stderr)

    # ------------------------------------------------------------------
    def _render_downloading(self, d: dict) -> None:
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        downloaded = d.get("downloaded_bytes", 0)
        speed = d.get("speed") or 0
        eta = d.get("eta") or 0

        # --- title (truncate to 40 chars) ---
        info = d.get("info_dict", {})
        title = info.get("title", "")
        if title and title != self._title:
            self._title = title
            print(f"\n[sodo] ↓ {title[:70]}")

        # --- bar ---
        if total:
            frac = min(downloaded / total, 1.0)
            filled = int(self.BAR_WIDTH * frac)
            bar = "█" * filled + "░" * (self.BAR_WIDTH - filled)
            pct = frac * 100
            size_mb = total / 1_048_576
            dl_mb = downloaded / 1_048_576
            speed_kb = speed / 1024
            line = (
                f"\r  [{bar}] {pct:5.1f}%  "
                f"{dl_mb:.1f}/{size_mb:.1f} MB  "
                f"{speed_kb:.0f} KB/s  ETA {eta}s  "
            )
        else:
            dl_mb = downloaded / 1_048_576
            speed_kb = speed / 1024
            bar = "·" * self.BAR_WIDTH
            line = f"\r  [{bar}]  {dl_mb:.1f} MB  {speed_kb:.0f} KB/s  "

        sys.stdout.write(line)
        sys.stdout.flush()

    # ------------------------------------------------------------------
    def _render_finished(self, d: dict) -> None:
        info = d.get("info_dict", {})
        filename = d.get("filename", "")
        title = info.get("title", filename) or filename
        total = d.get("total_bytes") or d.get("downloaded_bytes", 0)
        size_mb = total / 1_048_576 if total else 0.0
        bar = "█" * self.BAR_WIDTH
        print(
            f"\r  [{bar}] 100.0%  {size_mb:.1f} MB  done            ",
        )
