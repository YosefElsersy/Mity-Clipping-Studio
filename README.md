# Mity-Clipping-Studio

**Standalone Instagram Reel monitoring and video-processing tools by $mity.**

Mity-Clipping-Studio contains two independent Python scripts and a colored shell launcher. The Instagram monitor detects newly shared Reel cards in a selected Instagram Direct conversation and downloads the corresponding videos. The video processor prepares eligible source videos for vertical publishing by adding the configured watermark and cover image.

The tools are intentionally independent: downloading a Reel does **not** automatically start video processing. Use the launcher to choose which task to run.

## Features

### Instagram DM monitor

- Uses a dedicated persistent Google Chrome profile.
- The user signs in manually in the Chrome window.
- Monitors one selected Instagram Direct conversation.
- Detects newly inserted, visible Reel/clip cards using Instagram's web-page structure.
- Uses a left-side message-layout heuristic to identify incoming-looking cards. This is not verified sender identity.
- Opens the candidate card in a temporary tab and keeps the monitored conversation tab separate.
- Captures the shared Reel/post permalink and downloads it with `yt-dlp`.
- Uses cookies from the dedicated Chrome profile.
- Maintains a download archive, monitor state, and logs to help avoid duplicate downloads.

### Video processing

- Processes common video formats, including MP4, MOV, MKV, M4V, AVI, and WebM.
- Produces 1080 × 1920 (9:16) H.264 video at 30 FPS.
- Preserves the complete source image without stretching or cropping it.
- Adds a blurred, darkened background for videos that are not native 9:16.
- Applies the green-screen watermark using FFmpeg chroma key.
- Places `cover.jpg` on the first output frame only.
- Preserves source audio when present.
- Limits the output duration to the source video's duration.
- Skips existing outputs unless force mode is explicitly selected.
- Writes an FFmpeg log for each processed source video.

### Minimum video duration

The video processor enforces a **9.0-second minimum duration** using `ffprobe` before rendering:

| Source duration | Result |
|---|---|
| Less than 9.0 seconds (for example, 8.99 s) | Rejected from processing / skipped |
| Exactly 9.0 seconds | Eligible for processing |
| Greater than 9.0 seconds | Eligible for processing |
| Duration missing or invalid | Cannot be verified; processing fails safely |

The check uses the probed duration, not a rounded display value. The rule also applies in `--test`, `--batch`, and `--batch --force` modes. A short source file is **left in `input/reels/` unchanged**; it is not deleted or moved automatically. The minimum is currently defined in `process_videos.py` as `MIN_REEL_DURATION_SECONDS = 9.0`.

## Project structure

Clone or place the project at `~/Mity-Clipping-Studio`, because the supplied `run.sh` launcher expects that location.

```text
~/Mity-Clipping-Studio/
├── .gitignore
├── README.md
├── run.sh
│
├── instagram-dm/
│   ├── instagram_dm_monitor.py
│   ├── .venv/                   # Created locally; not committed
│   ├── monitor_state.json       # Created at runtime; not committed
│   ├── reel_links.txt           # Created at runtime; not committed
│   ├── yt_dlp_archive.txt      # Created at runtime; not committed
│   └── monitor.log              # Created at runtime; not committed
│
└── video-processing/
    ├── process_videos.py
    ├── input/
    │   ├── reels/                # Downloaded/source videos
    │   └── assets/
    │       ├── greenscreen.mp4   # Required watermark asset
    │       └── cover.jpg         # Required first-frame cover
    ├── output/                  # Rendered videos
    └── logs/                    # Per-video FFmpeg logs
```

The `.gitkeep` files preserve empty directories in Git. The `.venv`, downloaded videos, processed outputs, private assets, and runtime logs/state are excluded from Git by `.gitignore`.

## Requirements

- Ubuntu 24.04 (or a compatible Linux distribution).
- Python 3.10 or newer.
- Google Chrome Stable. The monitor launches the installed Chrome using Playwright's `channel="chrome"` option.
- FFmpeg and `ffprobe` for video processing.
- A working Instagram account that can access the target Direct conversation.
- The two required video assets: `greenscreen.mp4` and `cover.jpg`.

## Installation

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg
```

Install Google Chrome Stable if it is not already installed. Download it from the official page:

<https://www.google.com/chrome/>

Check the system tools:

```bash
google-chrome --version
ffmpeg -version
ffprobe -version
python3 --version
```

### 2. Get the project

```bash
git clone https://github.com/YosefElsersy/Mity-Clipping-Studio.git ~/Mity-Clipping-Studio
cd ~/Mity-Clipping-Studio
```

If the project is already cloned, simply enter the project directory:

```bash
cd ~/Mity-Clipping-Studio
```

### 3. Make the launcher executable

```bash
chmod +x run.sh
```

### 4. Create the Instagram monitor virtual environment

The monitor uses its own virtual environment inside `instagram-dm/`:

```bash
cd ~/Mity-Clipping-Studio/instagram-dm
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install playwright yt-dlp secretstorage
```

The monitor uses the installed Google Chrome browser, so the project does not require downloading a separate Playwright Chromium browser for this configuration.

Deactivate the virtual environment when finished setting it up:

```bash
deactivate
```

The video-processing script uses Python's standard library and the system `ffmpeg`/`ffprobe` commands; it does not require the monitor virtual environment.

### 5. Add the required assets

Create the assets directory if needed:

```bash
mkdir -p ~/Mity-Clipping-Studio/video-processing/input/assets
```

Place these two files there:

```text
video-processing/input/assets/greenscreen.mp4
video-processing/input/assets/cover.jpg
```

These assets are intentionally excluded from Git. Copy them into the project yourself; they are not downloaded automatically by the setup commands.

### 6. Create the remaining working directories

```bash
mkdir -p ~/Mity-Clipping-Studio/video-processing/input/reels
mkdir -p ~/Mity-Clipping-Studio/video-processing/output
mkdir -p ~/Mity-Clipping-Studio/video-processing/logs
```

## Run the unified shell menu

Start the colored launcher:

```bash
cd ~/Mity-Clipping-Studio
./run.sh
```

The launcher provides these options:

| Menu option | Action |
|---|---|
| 1 | Start the Instagram DM monitor |
| 2 | Process one eligible test video (minimum 9 seconds) |
| 3 | Process all eligible Reels (minimum 9 seconds) |
| 4 | Reprocess all eligible Reels, replacing existing outputs after successful rendering |
| 5 | Open the downloaded Reels folder |
| 6 | Open the processed videos folder |
| 7 | Open the FFmpeg logs folder |
| 8 | Check project files and dependencies |
| 0 | Exit |

The launcher returns to its menu after the selected script exits. The monitor itself remains active until you stop it with `Ctrl+C`.

## Run the Instagram monitor directly

Open a terminal and run:

```bash
cd ~/Mity-Clipping-Studio/instagram-dm
source .venv/bin/activate
python instagram_dm_monitor.py
```

In the dedicated Chrome window:

1. Sign in manually if required.
2. Open the intended person's conversation in the main pane.
3. Return to the terminal and select the Instagram tab shown by the monitor.
4. Confirm that the intended conversation is visibly open by typing `YES`.
5. Keep the conversation open while monitoring.

Newly downloaded Reels are saved to:

```text
~/Mity-Clipping-Studio/video-processing/input/reels/
```

The monitor continues to use this dedicated Chrome profile:

```text
~/.local/share/instagram-dm/chrome-profile
```

This keeps the existing browser login separate from the project directory. Do not share the Chrome profile, cookies, or authentication data.

The incoming-message detection is based on card position/layout and is not proof of the sender's identity. Instagram may change its web interface, which can affect detection. The monitor does not bypass login challenges, CAPTCHA, private-content restrictions, or other security checks.

## Run video processing directly

Run a single test using the first **eligible** video (9 seconds or longer):

```bash
cd ~/Mity-Clipping-Studio/video-processing
python3 process_videos.py --test
```

Process all eligible videos:

```bash
python3 process_videos.py --batch
```

Reprocess eligible videos and replace existing output files only after a successful render:

```bash
python3 process_videos.py --batch --force
```

The `--force` option does not bypass the 9-second minimum. Videos shorter than 9 seconds remain skipped.

Processed files are written to:

```text
~/Mity-Clipping-Studio/video-processing/output/
```

The output filename is based on the source name, with `_processed.mp4` appended. For example, `example.mp4` becomes `example_processed.mp4`.

FFmpeg logs are written to:

```text
~/Mity-Clipping-Studio/video-processing/logs/
```

## Typical workflow

The two scripts are independent and are not automatically chained together:

1. Start the Instagram monitor using option `1` in `./run.sh` (or run it directly).
2. Let it download shared Reels into `video-processing/input/reels/`.
3. Stop the monitor with `Ctrl+C` when you are ready to process the downloaded files.
4. Return to the launcher and choose option `2` for a test or option `3` for batch processing.
5. Review the rendered videos in `video-processing/output/`.

You can also keep the monitor running in one terminal and run video processing from a second terminal if you want both scripts active at the same time. Avoid processing a file while it is still being downloaded.

## Troubleshooting

### The launcher says the monitor virtual environment is missing

Create it and install the packages:

```bash
cd ~/Mity-Clipping-Studio/instagram-dm
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install playwright yt-dlp secretstorage
```

### Google Chrome is not detected

Install Google Chrome Stable from <https://www.google.com/chrome/> and verify that `google-chrome --version` works in the terminal.

### FFmpeg or ffprobe is missing

```bash
sudo apt update
sudo apt install -y ffmpeg
```

### Required assets are missing

Check that both files exist at the exact paths:

```bash
ls -lh ~/Mity-Clipping-Studio/video-processing/input/assets/
```

### A video is skipped as too short

This is expected when `ffprobe` reports a duration below 9.0 seconds. The source file is left unchanged in `input/reels/`; it is not processed.

### A video fails during rendering

Open the corresponding log file in `video-processing/logs/`. The log filename is based on the source video's name, for example `example_ffmpeg.log`.

### The monitor cannot use the Chrome profile

Close other Chrome processes using the dedicated monitor profile and start the monitor again. Sign in manually in the Chrome window opened by the script. Never copy or share the browser profile to troubleshoot authentication.

## Privacy and Git

The repository intentionally excludes:

- Python virtual environments.
- Downloaded Reel files.
- Processed output videos.
- `greenscreen.mp4` and `cover.jpg`.
- Chrome profile data and browser cookies.
- Runtime state, download archives, and logs.
- Local credential and secret files.

Before every Git commit or push, review the staged file list:

```bash
git status --short --untracked-files=all
```

Do not commit passwords, access tokens, browser profiles, session files, or private video assets.

## Current scope

This repository contains two standalone tools and a shell launcher. It does not currently provide an integrated background pipeline that automatically starts video processing immediately after a Reel download. It also does not include Instagram publishing/upload functionality. These are separate future features and should not be assumed to be available in this standalone version.

---

**Mity-Clipping-Studio — Built by $mity.**
