# sodo

> YouTube → MP3 & MP4 downloader — download audio and video playlists or tracks from anywhere on the command line.

## Install

```powershell
# from the project root (one-time setup)
pip install -e .
```

`sodo` requires **FFmpeg** to extract audio, embed metadata, and merge video streams.

* **Automatic Download**: When you run a download command for the first time, if FFmpeg is not found in your system `PATH` or `~/sodo/bin`, `sodo` will prompt you to automatically download and install it to `~/sodo/bin`.
* **Manual Installation**: You can download and install FFmpeg automatically to `~/sodo/bin` at any time:
  ```powershell
  sodo --install
  ```
* **Manual Uninstallation**: You can remove the downloaded binaries from `~/sodo/bin`:
  ```powershell
  sodo --uninstall
  ```
* **Custom / Global Installation**: Alternatively, you can add it to your system `PATH` manually or install via Gyan.FFmpeg:
  ```powershell
  winget install Gyan.FFmpeg
  ```
  or download from https://ffmpeg.org/download.html

## Usage

```powershell
sodo [OPTIONS] URL [URL ...]
```

### Options

| Flag | Description |
|------|-------------|
| `-m`, `--music` | MP3 audio mode (default; explicit flag for clarity) |
| `-v`, `--video` | MP4 video mode (downloads best video + audio and merges with FFmpeg) |
| `--mp4` | Alias for `-v` / `--video` |
| `-p`, `--playlist` | Download entire playlist (default when URL contains a playlist) |
| `--no-playlist` | Download single track only, even if the URL is part of a playlist |
| `--fmt FORMAT` | Choose format: `mp3`, `flac`, `wav`, `m4a`, `opus`, `mp4`, `webm` |
| `--pick` | Interactive format picker prompt before downloading |
| `--skip` | Download globally without requiring a local `.sodo` workspace |
| `-f`, `--force` | Force re-download even if already in global history |
| `-o`, `--output DIR` | Output directory (default: **current directory**) |
| `-q`, `--quiet` | Suppress chatter and progress bar |
| `--install` | Download and install FFmpeg to `~/sodo/bin` |
| `--uninstall` | Uninstall/remove FFmpeg from `~/sodo/bin` |
| `-V`, `--version` | Show version |
| `-h`, `--help` | Show help |

### Examples

```powershell
# Single track (MP3)
sodo "https://youtu.be/dQw4w9WgXcQ" --skip

# Single video as MP4
sodo -v "https://youtu.be/dQw4w9WgXcQ" --skip

# Download full playlist as MP3
sodo "https://www.youtube.com/playlist?list=PLrEnWoR732-BHrPp_CXxG0OBDAI8X-P0O" --skip

# Download full playlist as MP4 video
sodo -v "https://www.youtube.com/playlist?list=PLrEnWoR732-BHrPp_CXxG0OBDAI8X-P0O" --skip

# Watch URL inside a playlist: download full playlist
sodo -p "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrEnWoR732-BHrPp_CXxG0OBDAI8X-P0O" --skip

# Watch URL inside a playlist: download ONLY this single video
sodo --no-playlist "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrEnWoR732-BHrPp_CXxG0OBDAI8X-P0O" --skip

# Save to a specific folder
sodo -o "D:\Music" "URL" --skip
```

## What it does

1. **Smart Playlist Engine**: Automatically detects playlists (both direct `/playlist` and `/watch?v=...&list=...` links), previews total tracks and uploader, and downloads track-by-track.
2. **Global Deduplication**: Checks global history before each download. If 5 tracks of a 20-track playlist were already downloaded, they are skipped in `< 0.1s`.
3. **Resilient Downloads**: If an individual track in a playlist is blocked or unavailable, `sodo` records the failure and continues with the rest of the playlist.
4. **Rich Terminal Interface**:
   - Shows track progress: `↓ [3/24] Artist - Title  [video 1080p]`
   - Live download percentage, speed, and ETA
   - Real-time status for FFmpeg postprocessing (`⚙ Merging video + audio into MP4...`)
5. **Metadata & Quality**:
   - Converts to **MP3** (VBR highest quality) or merges to **MP4** with best video + audio streams
   - Embeds thumbnails as artwork and writes ID3/MP4 metadata tags
   - Windows-safe filename sanitization
