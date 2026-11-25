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
- Adds the transparent `watermark.png` creator mark near the bottom of the output.
- Places `cover.jpg` on the first output frame only.
- Preserves source audio when present.
- Limits the output duration to the source video's duration.
- Skips existing outputs unless force mode is explicitly selected.
- Writes an FFmpeg log for each processed source video.

### Minimum video duration

The video processor enforces a **9.0-second minimum duration** using `ffprobe` before rendering:

| Source duration | Result |
|---|---|
| Less than 9.0 seconds (for example, 8.99 s) | Moved automatically to `input/rejected/`; not rendered |
| Exactly 9.0 seconds | Eligible for processing |
| Greater than 9.0 seconds | Eligible for processing |
| Duration or video stream cannot be verified | Moved to `input/rejected/` for manual review |

The check uses the probed duration, not a rounded display value. The rule also applies in `--test`, `--batch`, and `--batch --force` modes. A source shorter than 9 seconds is moved to `input/rejected/`; files whose duration or video stream cannot be verified are also moved there for manual review. Files that fail during FFmpeg rendering remain in `input/reels/` so they can be retried. The minimum is currently defined in `process_videos.py` as `MIN_REEL_DURATION_SECONDS = 9.0`.

## Project structure

Clone or place the project at `~/Mity-Clipping-Studio`, because the supplied `run.sh` launcher expects that location.

```text
~/Mity-Clipping-Studio/
├── .gitignore
├── README.md
├── run.sh
├── rename_videos.py          # Numbers output and rejected videos for upload
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
    │   ├── rejected/             # Videos under 9 seconds or files that cannot be verified
    │   └── assets/
    │       ├── greenscreen.mp4   # Required top green-screen overlay (user-supplied)
    │       ├── cover.jpg         # Required first-frame cover (user-supplied)
    │       └── watermark.png     # Required transparent creator mark (default included)
    ├── output/                  # Rendered videos
    └── logs/                    # Per-video FFmpeg logs
```

The `.gitkeep` files preserve empty directories in Git. The `.venv`, downloaded videos, processed outputs, private user-supplied assets, and runtime logs/state are excluded from Git by `.gitignore`. The repository includes a default `watermark.png` file.

## Requirements

- Ubuntu 24.04 (or a compatible Linux distribution).
- Python 3.10 or newer.
- Google Chrome Stable. The monitor launches the installed Chrome using Playwright's `channel="chrome"` option.
- FFmpeg and `ffprobe` for video processing.
- A working Instagram account that can access the target Direct conversation.
- Three required video-processing assets in `video-processing/input/assets/`: `greenscreen.mp4`, `cover.jpg`, and `watermark.png`. The repository includes a default `watermark.png`; the user must supply `greenscreen.mp4` and `cover.jpg`.

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

The video processor requires **all three files** with these exact names inside `video-processing/input/assets/`:

```text
video-processing/input/assets/
├── greenscreen.mp4
├── cover.jpg
└── watermark.png
```

| File | Purpose | What the user must do |
|---|---|---|
| `greenscreen.mp4` | Green-screen overlay placed near the top; FFmpeg removes the green background using chroma key. | Supply your own green-screen video. The green background should reach the frame edges for reliable key-color detection. |
| `cover.jpg` | Replaces the first output frame only. | Supply your own cover image. |
| `watermark.png` | Transparent creator/brand mark placed near the bottom of the video. | A default file is included in this repository. You can keep it or replace it with your own transparent PNG, but keep the exact filename `watermark.png`. |

**Important:** All three files must exist before running video processing. Filenames are case-sensitive on Linux. `greenscreen.mp4` and `cover.jpg` are user-supplied private assets and are not included in Git. The default `watermark.png` is included in the repository. The installer does not download or create replacements for missing assets.

### 6. Create the remaining working directories

```bash
mkdir -p ~/Mity-Clipping-Studio/video-processing/input/reels
mkdir -p ~/Mity-Clipping-Studio/video-processing/input/rejected
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
| 9 | Rename videos in `output/` and `input/rejected/` for upload (each folder numbered separately) |
| 10 | Open rejected videos |
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

The `--force` option does not bypass the 9-second minimum. Videos shorter than 9 seconds are moved automatically from `input/reels/` to `input/rejected/`. Files whose duration or video stream cannot be verified are also moved to `input/rejected/` for manual review. Files that fail during FFmpeg rendering remain in `input/reels/` so they can be retried.

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
5. Review the rendered videos in `video-processing/output/`. Videos that are too short or cannot be verified are moved to `video-processing/input/rejected/`.
6. When the videos are ready for uploading, choose option `9` to number the videos in `output/` and `input/rejected/`. Each folder is numbered independently; review the proposed names before confirming.

You can also keep the monitor running in one terminal and run video processing from a second terminal if you want both scripts active at the same time. Avoid processing a file while it is still being downloaded.

## Instagram Reel upload automation (experimental)

The optional uploader uses Playwright to operate Instagram's visible desktop website in Chrome. It is an experimental UI workflow, not an official Instagram publishing integration. Instagram's terms restrict automated access without express permission; account restrictions or UI changes are possible. The uploader does not use private APIs, stealth techniques, or CAPTCHA/login-challenge bypasses, and it stops if a security checkpoint or activity warning appears. Use it only if you understand and accept those risks.

Before opening Chrome, it asks for one caption (used for every Reel in that run), then checks the inventory:

- At least **38 MP4 files** in `video-processing/input/rejected/`.
- At least **120 MP4 files** in `video-processing/output/`.

The configured schedule is:

| Batch | Source | Videos | Wait after batch |
|---|---|---:|---:|
| 1 | `rejected/` | 19 | 2 hours |
| 2 | `rejected/` | 19 | 4 hours |
| 3 | `output/` | 19 | 3 hours |
| 4 | `output/` | 20 | 4 hours |
| 5 | `output/` | 20 | 2 hours |
| 6 | `output/` | 20 | 2 hours |
| 7 | `output/` | 20 | Finish |

**Count clarification:** this exact schedule publishes 38 rejected videos and **99 output videos**, not 120 output videos. With exactly 120 output files, 21 remain unused. The preflight threshold is 120 as requested; the script does not invent extra batches.

Each Reel is handled in a fresh browser tab. The crop step selects Portrait `9:16`. Rejected videos use `video-processing/input/assets/cover.jpg` as an uploaded cover; processed output videos do not get an additional cover because their cover is already included in the rendered video. The caption is filled before Share. A 30-second pause is used between individual posts, and a visible countdown runs during the scheduled batch gaps.

The uploader uses a separate Chrome profile at `~/.local/share/mity-clipping-studio/instagram-upload-profile`; sign in manually. Confirmed uploads and the next scheduled batch are stored locally in `instagram-upload/upload_state.json` so a stopped run can be resumed without automatically repeating confirmed posts. If confirmation is uncertain, inspect Instagram before resuming.

Use menu option **11** for a caption prompt, inventory check, and schedule preview without opening Chrome. Use option **12** to start the full workflow. To test the rejected-video path with one Reel, run:

```bash
instagram-dm/.venv/bin/python instagram-upload/instagram_reel_uploader.py --test-one
```

The first interaction is the caption prompt. The script then requires explicit typed confirmations before launching the browser and publishing. Do not run a full schedule until the one-Reel test is verified.

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

Check that all three required files exist with the exact names:

```bash
ls -lh ~/Mity-Clipping-Studio/video-processing/input/assets/{greenscreen.mp4,cover.jpg,watermark.png}
```

The repository supplies the default `watermark.png`. You must add `greenscreen.mp4` and `cover.jpg` yourself. Keep the filenames and letter case unchanged.

### A video is skipped as too short

This is expected when `ffprobe` reports a duration below 9.0 seconds. The source file is moved automatically from `input/reels/` to `input/rejected/`; it is not processed.

### A video fails during rendering

Open the corresponding log file in `video-processing/logs/`. The log filename is based on the source video's name, for example `example_ffmpeg.log`.

### The monitor cannot use the Chrome profile

Close other Chrome processes using the dedicated monitor profile and start the monitor again. Sign in manually in the Chrome window opened by the script. Never copy or share the browser profile to troubleshoot authentication.

## Privacy and Git

The repository intentionally excludes:

- Python virtual environments.
- Downloaded Reel files.
- Processed output videos.
- `greenscreen.mp4` and `cover.jpg` (private user-supplied assets).
- The default `watermark.png` is included in the repository; users may replace it with their own transparent PNG while keeping the same filename.
- Chrome profile data and browser cookies.
- Runtime state, download archives, and logs.
- Local credential and secret files.

Before every Git commit or push, review the staged file list:

```bash
git status --short --untracked-files=all
```

Do not commit passwords, access tokens, browser profiles, session files, or private video assets.

## Current scope

This repository contains standalone monitoring and video-processing tools, a shell launcher, and an experimental browser-driven Instagram Reel uploader. Downloading and video processing remain separate steps; the uploader is not an official Meta integration and may be affected by Instagram UI changes or account restrictions.

---

**Mity-Clipping-Studio — Built by $mity.**
