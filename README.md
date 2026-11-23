# Mity-Clipping-Studio

**Standalone Instagram Reel monitoring and video-processing tools by $mity.**

Mity-Clipping-Studio contains two independent Python scripts and native launchers for Linux and Windows. The Instagram monitor watches one selected Instagram Direct conversation and downloads newly shared Reel cards. The video processor prepares eligible source videos for vertical publishing.

The tools are intentionally independent: downloading a Reel does **not** automatically start video processing. Use the launcher to choose which task to run. This test package includes the 8.5.1 monitor patch that removes persistent structural-card deduplication while preserving URL-based duplicate-download protection.

## Features

### Instagram DM monitor

- Uses a dedicated persistent Google Chrome profile.
- The user signs in manually in the Chrome window.
- Monitors one selected Instagram Direct conversation.
- Detects newly inserted, visible Reel/clip cards using Instagram's web-page structure.
- Uses a left-side message-layout heuristic to identify incoming-looking cards. This is not verified sender identity.
- Opens the candidate card in a temporary tab and keeps the monitored conversation tab separate.
- Captures the shared Reel/post permalink and downloads it with `yt-dlp`.
- Reads cookies from the dedicated Chrome profile.
- Maintains a download archive, monitor state, and logs. Duplicate downloads are prevented using captured Reel/post URLs rather than card-layout signatures, which can be identical for different newly received Reels.
- Uses the existing Linux Chrome profile path to preserve a previous login. On Windows, the dedicated profile is stored in the user's Local AppData directory.

### Video processing

- Processes common video formats, including MP4, MOV, MKV, M4V, AVI, and WebM.
- Produces 1080 × 1920 (9:16) H.264 video at 30 FPS.
- Preserves the complete source image without stretching or cropping it.
- Adds a blurred, darkened background for videos that are not native 9:16.
- Applies the green-screen watermark using FFmpeg chroma key.
- Places `cover.jpg` on the first output frame only.
- Preserves source audio when present.
- Limits output duration to the source video's duration.
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

The check uses the probed duration, not a rounded display value. The rule applies in `--test`, `--batch`, and `--batch --force` modes. A short source file is **left in `input/reels/` unchanged**; it is not deleted or moved automatically. The default minimum is defined in `video-processing/process_videos.py` as `MIN_REEL_DURATION_SECONDS = 9.0`.

## Project structure

The launchers resolve all project paths relative to their own location. You can clone the repository into any directory; `~/Mity-Clipping-Studio` is the suggested location, not a hard requirement.

```text
Mity-Clipping-Studio/
├── .gitattributes
├── .gitignore
├── README.md
├── requirements.txt
├── setup.sh                 # Linux installer
├── run.sh                   # Linux launcher
├── setup.ps1                # Windows installer
├── run.ps1                  # Windows launcher
│
├── instagram-dm/
│   ├── instagram_dm_monitor.py
│   └── .venv/                # Created locally; not committed
│
└── video-processing/
    ├── process_videos.py
    ├── input/
    │   ├── reels/            # Downloaded/source videos
    │   ├── staging/          # Reserved for temporary downloads
    │   ├── rejected/         # Reserved for rejected videos
    │   └── assets/
    │       ├── greenscreen.mp4   # Required watermark asset (user-supplied)
    │       └── cover.jpg         # Required first-frame cover (user-supplied)
    ├── output/               # Rendered videos
    └── logs/                 # Per-video FFmpeg logs
```

Runtime files such as monitor state, download archives, logs, virtual environments, downloaded videos, rendered videos, and private assets are excluded from Git by `.gitignore`.

## Requirements

### Required for both operating systems

- 64-bit Windows 10/11 or a compatible Linux distribution.
- Python **3.11 or newer**.
- Internet access during first-time setup to install Python packages.
- Google Chrome Stable for the Instagram monitor.
- FFmpeg and `ffprobe` for video processing.
- An Instagram account with access to the target Direct conversation.
- The two required user-supplied assets: `greenscreen.mp4` and `cover.jpg`.

### Python packages

The installer creates a virtual environment at `instagram-dm/.venv` and installs the packages listed in `requirements.txt`:

- `playwright`
- `yt-dlp`
- `secretstorage` on Linux only (for access to the Linux desktop keyring when yt-dlp reads Chrome cookies).

The video processor uses Python's standard library plus the external FFmpeg executables. It does not require a separate Python video-editing package.

### Why the installer does not download Playwright Chromium

The monitor launches the branded Google Chrome installation through Playwright's `channel="chrome"` option. Therefore, setup installs the Playwright Python package and checks for Google Chrome Stable; it does not download a separate Playwright Chromium browser build. See the [Playwright browser documentation](https://playwright.dev/python/docs/browsers).

## Installation — Ubuntu / Debian Linux

### 1. Clone the repository

```bash
git clone https://github.com/YosefElsersy/Mity-Clipping-Studio.git
cd Mity-Clipping-Studio
```

You may place the project in a different directory; the launchers resolve paths relative to the project folder.

### 2. Run the installer

```bash
chmod +x setup.sh run.sh
./setup.sh
```

The installer:

1. Checks for Python 3.11 or newer. If it is missing, it can offer to install the distribution Python, venv, and pip packages using `apt`.
2. Creates `instagram-dm/.venv` if it does not already exist.
3. Upgrades pip inside that environment.
4. Installs `requirements.txt` into that environment.
5. Creates the project input, output, and log directories.
6. Checks for Google Chrome Stable, FFmpeg, and `ffprobe`.
7. On Debian/Ubuntu systems, offers to install missing Google Chrome and/or FFmpeg using `apt` and `sudo`. It asks before running privileged package-manager commands.
8. Checks whether the required user assets are present.

If the installer asks whether to install Python or system dependencies, answer `Y` to approve or `n` to skip. If skipped, install the missing tool manually and rerun the setup check.

### 3. Add your private assets

Place your own files at these exact paths:

```text
video-processing/input/assets/greenscreen.mp4
video-processing/input/assets/cover.jpg
```

These files are private/user-supplied assets and are intentionally excluded from Git. The installer does not download or create replacement assets.

### 4. Launch the menu

```bash
./run.sh
```

On the first launch, `run.sh` checks the virtual environment and required Python packages. If they are missing, it offers to run `setup.sh` automatically. After the first-time setup succeeds, later launches go directly to the menu. You can skip this automatic setup prompt by setting `MITY_SKIP_AUTO_SETUP=1`.

## Installation — Windows 10 / 11

Use Windows PowerShell or Windows Terminal.

### 1. Clone the repository

```powershell
git clone https://github.com/YosefElsersy/Mity-Clipping-Studio.git
cd Mity-Clipping-Studio
```

### 2. Run the installer

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

The execution-policy command applies only to the current PowerShell process; it does not permanently change the system policy.

The installer:

1. Checks for Python 3.11 or newer. If it is missing and WinGet is available, it offers to install Python 3.12 using `Python.Python.3.12`.
2. Creates `instagram-dm\.venv`.
3. Installs the Python packages from `requirements.txt`.
4. Creates the project directories.
5. Checks for Google Chrome Stable and FFmpeg/`ffprobe`.
6. If `winget` is available, offers to install missing system dependencies using the package IDs `Google.Chrome` and `Gyan.FFmpeg`. It asks before installing.
7. Checks for the required user-supplied assets.

If WinGet is unavailable, install the missing system tools manually:

- [Google Chrome](https://www.google.com/chrome/)
- [FFmpeg Windows builds](https://www.gyan.dev/ffmpeg/builds/)

After WinGet installs a system tool, close and reopen PowerShell if the current session does not yet see the updated PATH.

### 3. Add your private assets

Place your own files at:

```text
video-processing\input\assets\greenscreen.mp4
video-processing\input\assets\cover.jpg
```

### 4. Launch the menu

```powershell
.\run.ps1
```

On the first launch, `run.ps1` checks the virtual environment and required Python packages. If they are missing, it offers to run `setup.ps1` automatically. After first-time setup succeeds, later launches go directly to the menu. You can skip this automatic setup prompt by setting `$env:MITY_SKIP_AUTO_SETUP = '1'`.

If PowerShell blocks the script, use the process-scoped execution-policy command shown above, then run `run.ps1` again.

## Launcher menu

Both launchers provide equivalent options:

| Option | Action |
|---|---|
| 1 | Start the Instagram DM monitor |
| 2 | Process one eligible test video (minimum 9 seconds) |
| 3 | Process all eligible Reels (minimum 9 seconds) |
| 4 | Reprocess eligible Reels, replacing existing outputs after successful rendering |
| 5 | Open the downloaded Reels folder |
| 6 | Open the processed videos folder |
| 7 | Open the FFmpeg logs folder |
| 8 | Check project files and dependencies |
| 0 | Exit |

The launcher returns to its menu after the selected script exits. The monitor remains active until you stop it with `Ctrl+C`.

## Instagram DM monitor

The monitor can be started from option `1` in the launcher or directly.

### Linux direct launch

```bash
cd instagram-dm
source .venv/bin/activate
python instagram_dm_monitor.py
```

### Windows direct launch

```powershell
cd instagram-dm
.\.venv\Scripts\Activate.ps1
python .\instagram_dm_monitor.py
```

In the dedicated Chrome window:

1. Sign in manually if required.
2. Open the intended person's conversation in the main pane.
3. Return to the terminal and select the Instagram tab shown by the monitor.
4. Confirm that the intended conversation is visibly open by typing `YES`.
5. Keep the conversation open while monitoring.

Newly downloaded Reels are saved to:

```text
video-processing/input/reels/
```

The dedicated Chrome profile locations are:

- Linux: `~/.local/share/instagram-dm/chrome-profile` (kept unchanged to reuse an existing login).
- Windows: `%LOCALAPPDATA%\Mity-Clipping-Studio\instagram-dm\chrome-profile`.

This keeps browser login data outside the Git repository. Do not share the Chrome profile, cookies, or authentication data.

The incoming-message detection is based on card position/layout and is not proof of the sender's identity. Instagram may change its web interface, which can affect detection. The monitor does not bypass login challenges, CAPTCHA, private-content restrictions, or other security checks.

## Video processing

Run a single test using the first **eligible** video (9 seconds or longer).

### Linux

```bash
cd video-processing
python3 process_videos.py --test
python3 process_videos.py --batch
python3 process_videos.py --batch --force
```

### Windows

```powershell
cd video-processing
python process_videos.py --test
python process_videos.py --batch
python process_videos.py --batch --force
```

Use `--batch --force` only when you intentionally want to replace existing outputs. It does not bypass the 9-second minimum.

The `--test` mode selects the first eligible video, not necessarily the first filename in the directory. Short videos remain in `input/reels/` unchanged and are skipped. The processor never deletes original source videos.

Processed files are written to `video-processing/output/`. Output filenames append `_processed.mp4` to the source filename. FFmpeg logs are written to `video-processing/logs/`.

## Typical workflow

The two scripts are independent and are not automatically chained together:

1. Start the Instagram monitor using option `1` in the launcher.
2. Let it download shared Reels into `video-processing/input/reels/`.
3. Stop the monitor with `Ctrl+C` when ready to process.
4. Return to the launcher and choose option `2` for a test or option `3` for batch processing.
5. Review the rendered videos in `video-processing/output/`.

You can also keep the monitor running in one terminal and run video processing from a second terminal. Avoid processing a file while it is still being downloaded.

## Troubleshooting

### Python virtual environment is missing

Rerun the platform setup script:

- Linux: `./setup.sh`
- Windows: `.\setup.ps1` (from PowerShell)

### Google Chrome is not detected

Install Google Chrome Stable from <https://www.google.com/chrome/>. The monitor uses Playwright's installed Chrome channel and does not use a separate downloaded Chromium build.

### FFmpeg or ffprobe is missing

- Ubuntu/Debian: `sudo apt update && sudo apt install -y ffmpeg`
- Windows: use the [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/) or install the `Gyan.FFmpeg` WinGet package.

After changing system PATH on Windows, reopen PowerShell.

### Required assets are missing

Check that both files exist in `video-processing/input/assets/`:

- `greenscreen.mp4`
- `cover.jpg`

### A video is skipped as too short

This is expected when `ffprobe` reports a duration below 9.0 seconds. The source file is left unchanged in `input/reels/` and is not processed.

### A video fails during rendering

Open the corresponding log file in `video-processing/logs/`. The log filename is based on the source video's name, for example `example_ffmpeg.log`.

### The monitor cannot use the Chrome profile

Close other Chrome processes using the dedicated monitor profile and start the monitor again. Sign in manually in the Chrome window opened by the script. Never copy or share the browser profile to troubleshoot authentication.

### Windows PowerShell blocks the launcher

In the current PowerShell window, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then run `.\run.ps1` again.

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

This repository contains two standalone tools and platform-specific launchers/installers. It does not currently provide an integrated background pipeline that automatically starts video processing immediately after a Reel download. It also does not include Instagram publishing/upload functionality or the optional `ig_login.py` utility.

---

**Mity-Clipping-Studio — Built by $mity.**
