"""sodo – YouTube audio downloader CLI."""

import sys

# Windows consoles default to cp1252 which can't encode arrows, checkmarks,
# and other Unicode used in sodo's output. Reconfigure to UTF-8 at startup.
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

__version__ = "0.2.0"
__author__ = "asim"
