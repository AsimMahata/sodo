# sodo

> YouTube → MP3 downloader — download audio from anywhere on the command line.

## Install

```powershell
# from the project root (one-time setup)
pip install -e .
```

`sodo` requires **FFmpeg** to extract audio and embed metadata.

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

```
sodo [OPTIONS] URL [URL ...]
```

### Options

| Flag | Description |
|------|-------------|
| `-m`, `--music` | MP3 mode (default; explicit flag for clarity) |
| `-o`, `--output DIR` | Output directory (default: **current directory**) |
| `-q`, `--quiet` | Suppress yt-dlp chatter |
| `--install` | Download and install FFmpeg to `~/sodo/bin` |
| `--uninstall` | Uninstall/remove FFmpeg from `~/sodo/bin` |
| `-V`, `--version` | Show version |
| `-h`, `--help` | Show help |

### Examples

```powershell
# Single track — saved in the folder you're in
sodo "https://youtu.be/dQw4w9WgXcQ"

# Multiple tracks with explicit music flag
sodo -m "URL1" "URL2" "URL3"

# Save to a specific folder
sodo -o "D:\Music" "URL"
```

## What it does

1. Fetches the best available audio stream via **yt-dlp**
2. Converts to **MP3** (VBR best quality) via **FFmpeg**
3. Embeds **thumbnail** as album art
4. Embeds **title, uploader, upload date** as ID3 metadata
5. Shows a clean **progress bar** per track
6. Saves with the **original video title** (Windows-safe filename)
7. Exits non-zero if any download fails
