# Mity-Clipping-Studio — Standalone Scripts

Place the files in this layout:

```text
~/Mity-Clipping-Studio/
├── instagram-dm/
│   └── instagram_dm_monitor.py
└── video-processing/
    ├── process_videos.py
    ├── input/
    │   ├── reels/
    │   └── assets/
    │       ├── greenscreen.mp4
    │       └── cover.jpg
    ├── output/
    └── logs/
```

## Instagram DM monitor

```bash
cd ~/Mity-Clipping-Studio/instagram-dm
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install playwright yt-dlp secretstorage
python instagram_dm_monitor.py
```

The monitor keeps using its existing dedicated Chrome profile at
`~/.local/share/instagram-dm/chrome-profile` so an existing browser login can be reused.
It writes its monitor state and logs under `~/Mity-Clipping-Studio/instagram-dm`
and downloads Reels to `~/Mity-Clipping-Studio/video-processing/input/reels`.

## Video processing

```bash
cd ~/Mity-Clipping-Studio/video-processing
python3 process_videos.py --test
python3 process_videos.py --batch
```

Use `--batch --force` only when you intentionally want to replace existing outputs.
The processor resolves `input/`, `output/`, and `logs/` relative to the folder
containing `process_videos.py`.

Required assets: `input/assets/greenscreen.mp4` and `input/assets/cover.jpg`.
System requirements: Python 3, Google Chrome, FFmpeg, and ffprobe.
