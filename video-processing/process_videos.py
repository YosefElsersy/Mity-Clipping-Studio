#!/usr/bin/env python3
"""Batch-compose Instagram Reels with an auto-sized blurred background.

Project layout (relative to this script):
  input/reels/*                 Source reels (square, portrait, or landscape)
  input/assets/greenscreen.mp4  VAVADA green-screen watermark video
  input/assets/cover.jpg        Image used for output frame 0 only
  output/                       Processed videos
  logs/                         FFmpeg logs

Examples:
  python3 process_videos.py --test --force       # one sample only
  python3 process_videos.py --batch              # every video; skip existing outputs
  python3 process_videos.py --batch --force      # every video; replace existing outputs

Composition:
- Output is always 1080x1920 (9:16), 30 FPS, H.264.
- Exact 9:16 inputs fill the canvas edge-to-edge without changing aspect ratio.
- Other aspect ratios are preserved in full and centered over a blurred,
  darkened, full-screen copy of that reel. Square 1:1 inputs therefore become
  a sharp 1080x1080 centered video with blurred fill above and below.
- The greenscreen watermark is keyed to transparency and overlaid near the top.
- cover.jpg replaces frame zero only; it does not add duration.
- Original reel audio is retained when present.
- Output duration is capped to the source Reel duration; a longer watermark clip
  cannot add frozen frames at the end.

The script never modifies source files. Existing output files are skipped unless
--force is supplied. A new output replaces an old one only after encoding succeeds.
--test processes the first eligible input; --batch processes all eligible inputs (9 seconds or longer).
Shorter videos are rejected before rendering and their source files are kept unchanged.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REELS_DIR = ROOT / "input" / "reels"
ASSETS_DIR = ROOT / "input" / "assets"
OVERLAY_FILE = ASSETS_DIR / "greenscreen.mp4"
COVER_FILE = ASSETS_DIR / "cover.jpg"
OUTPUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "logs"
SUPPORTED_SUFFIXES = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm"}
OUT_W = 1080
OUT_H = 1920
OUT_FPS = 30
TARGET_AR = OUT_W / OUT_H
MIN_REEL_DURATION_SECONDS = 9.0


def run_probe(path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_aspect_ratio,display_aspect_ratio,sample_rate,channels",
        "-of", "json", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path.name}: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse ffprobe output for {path.name}") from exc


def media_duration(probe: dict[str, Any]) -> float:
    try:
        return float(probe.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        return 0.0


def is_duration_eligible(duration: float) -> bool:
    """Return True only when a video meets the mandatory 9-second minimum."""
    return duration >= MIN_REEL_DURATION_SECONDS


def first_video_stream(probe: dict[str, Any]) -> dict[str, Any]:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise RuntimeError("No video stream found.")


def has_audio(probe: dict[str, Any]) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe.get("streams", []))


def validate_inputs() -> None:
    missing = [p for p in (REELS_DIR, OVERLAY_FILE, COVER_FILE) if not p.exists()]
    if missing:
        lines = "\n".join(f"  - {p}" for p in missing)
        raise FileNotFoundError(f"Required input path(s) not found:\n{lines}")
    if not REELS_DIR.is_dir():
        raise NotADirectoryError(f"Reels path is not a directory: {REELS_DIR}")


def _extract_rgb_frame(path: Path, timestamp: float, width: int, height: int) -> bytes:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, timestamp):.3f}",
        "-i", str(path), "-frames:v", "1", "-an", "-sn", "-dn",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    expected = width * height * 3
    if result.returncode != 0 or len(result.stdout) != expected:
        detail = result.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(
            f"Could not sample a frame from {path.name} at {timestamp:.2f}s. {detail}"
        )
    return result.stdout


def detect_key_color(path: Path) -> str:
    """Estimate green-screen background RGB from several outer-border samples."""
    probe = run_probe(path)
    stream = first_video_stream(probe)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    duration = media_duration(probe)
    if width < 16 or height < 16 or duration <= 0:
        raise RuntimeError("Green-screen video has invalid dimensions or duration.")

    timestamps = sorted({
        min(max(duration * fraction, 0.05), max(0.05, duration - 0.05))
        for fraction in (0.08, 0.25, 0.50, 0.75, 0.92)
    })
    border_x = max(3, int(width * 0.08))
    border_y = max(3, int(height * 0.06))
    sampled: list[tuple[int, int, int]] = []
    step = 3

    for timestamp in timestamps:
        frame = _extract_rgb_frame(path, timestamp, width, height)
        for y in range(0, height, step):
            for x in range(0, width, step):
                if not (x < border_x or x >= width - border_x or y < border_y or y >= height - border_y):
                    continue
                offset = (y * width + x) * 3
                r, g, b = frame[offset], frame[offset + 1], frame[offset + 2]
                if g >= 35 and g > r * 1.18 and g > b * 1.12:
                    sampled.append((r, g, b))

    if len(sampled) < 100:
        raise RuntimeError(
            "Could not confidently detect green in the outer border of greenscreen.mp4. "
            "Make sure the green background reaches the frame edges, or use --key-color 0xRRGGBB."
        )

    red = int(statistics.median(pixel[0] for pixel in sampled))
    green = int(statistics.median(pixel[1] for pixel in sampled))
    blue = int(statistics.median(pixel[2] for pixel in sampled))
    return f"0x{red:02X}{green:02X}{blue:02X}"


def build_filter_graph(
    args: argparse.Namespace, key_color: str, source_ar: float, reel_duration: float
) -> tuple[str, str]:
    """Return a duration-bounded filter graph and a description of the reel layout."""
    duration_text = f"{reel_duration:.6f}"
    if abs(source_ar - TARGET_AR) <= args.portrait_tolerance:
        # A true 9:16 Reel needs no background fill: scale it to the canvas
        # while preserving the full image and avoiding any crop or distortion.
        base = (
            "[0:v]"
            f"trim=duration={duration_text},setpts=PTS-STARTPTS,"
            f"scale={OUT_W}:{OUT_H}:flags=lanczos,"
            f"setsar=1,fps={OUT_FPS}"
            "[base]"
        )
        layout = "native 9:16: full-screen, aspect ratio preserved"
    else:
        # Fill the canvas using a blurred/dimmed copy, then place the complete
        # sharp original in the largest rectangle that fits the 9:16 canvas.
        # A square source becomes 1080x1080 in the middle, with blurred fill
        # above and below. Wider/taller non-9:16 sources are treated likewise.
        base = (
            "[0:v]"
            f"trim=duration={duration_text},setpts=PTS-STARTPTS,split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={OUT_W}:{OUT_H},boxblur={args.background_blur}:2,"
            f"eq=brightness={args.background_brightness:.3f}:saturation={args.background_saturation:.3f},"
            f"setsar=1,fps={OUT_FPS}[bg];"
            f"[fgsrc]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:"
            f"force_divisible_by=2:flags=lanczos,setsar=1,fps={OUT_FPS}[sharp];"
            "[bg][sharp]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1:format=auto[base]"
        )
        layout = "blurred full-screen background + complete sharp original centered"

    # Keep the successful VAVADA watermark sizing/positioning. Convert to RGBA
    # before RGB colorkey so FFmpeg has an alpha channel to remove the green.
    foreground = (
        "[1:v]"
        f"trim=duration={duration_text},setpts=PTS-STARTPTS,fps=30,"
        f"scale={args.overlay_width}:-2:flags=lanczos,"
        "format=rgba,"
        f"colorkey={key_color}:{args.similarity:.3f}:{args.blend:.3f},"
        "format=yuva444p[fg]"
    )

    overlay_x = "(W-w)/2" if args.overlay_x == "center" else args.overlay_x
    composite = (
        f"[base][fg]overlay=x={overlay_x}:y={args.overlay_y}:"
        "eof_action=repeat:shortest=0:format=auto,"
        f"trim=duration={duration_text},setpts=PTS-STARTPTS[comp]"
    )

    # Cover image replaces output frame 0 only; no extra duration is added.
    cover = (
        f"[2:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUT_W}:{OUT_H},setsar=1,format=rgba[cover]"
    )
    first_frame = (
        "[comp][cover]overlay=0:0:enable='eq(n,0)':"
        "eof_action=repeat:shortest=0:format=auto,"
        f"trim=duration={duration_text},setpts=PTS-STARTPTS,"
        "scale=in_range=full:out_range=tv,format=yuv420p,setparams=range=limited[outv]"
    )
    return ";".join((base, foreground, composite, cover, first_frame)), layout


def output_path_for(reel: Path) -> Path:
    return OUTPUT_DIR / f"{reel.stem}_processed.mp4"


def process_one(
    reel: Path, args: argparse.Namespace, base_probe: dict[str, Any] | None = None
) -> Path | None:
    output = output_path_for(reel)
    temp_output = output.with_name(f"{output.stem}.partial{output.suffix}")
    log_path = LOG_DIR / f"{reel.stem}_ffmpeg.log"

    # Validate duration before checking existing outputs. Even force mode must
    # never render a source shorter than the mandatory minimum.
    base_probe = base_probe if base_probe is not None else run_probe(reel)
    duration = media_duration(base_probe)
    if duration <= 0:
        raise RuntimeError(f"Could not determine a valid duration for {reel.name}")
    if not is_duration_eligible(duration):
        raise RuntimeError(
            f"Rejected: {reel.name} is {duration:.3f}s; minimum is "
            f"{MIN_REEL_DURATION_SECONDS:.1f}s."
        )

    if output.exists() and not args.force:
        print(f"Skipping (output already exists): {output.name}")
        return None

    source_stream = first_video_stream(base_probe)
    source_w = int(source_stream.get("width") or 0)
    source_h = int(source_stream.get("height") or 0)
    if source_w <= 0 or source_h <= 0:
        raise RuntimeError(f"Invalid video dimensions for {reel.name}: {source_w}x{source_h}")
    source_ar = source_w / source_h

    key_color = args.key_color if args.key_color != "auto" else detect_key_color(OVERLAY_FILE)
    graph, layout = build_filter_graph(args, key_color, source_ar, duration)

    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", str(reel), "-i", str(OVERLAY_FILE), "-i", str(COVER_FILE),
        "-filter_complex", graph,
        "-map", "[outv]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-r", str(OUT_FPS), "-fps_mode", "cfr",
        "-c:a", "aac", "-b:a", args.audio_bitrate,
        "-movflags", "+faststart", "-map_metadata", "0",
        # Hard cap the output to the reel's probed duration. This prevents a
        # longer greenscreen/watermark asset from extending the finished Reel.
        "-t", f"{duration:.6f}",
        "-progress", "pipe:1", "-nostats", str(temp_output),
    ]

    print(f"\nProcessing: {reel.name}")
    print(f"Input dimensions: {source_w}x{source_h} (aspect ratio {source_ar:.5f})")
    print(f"Reel layout: {layout}")
    print(f"Detected chroma key color: {key_color}")
    print(f"Watermark source width: {args.overlay_width}px; position y={args.overlay_y}px")
    print(f"RGB colorkey similarity: {args.similarity:.2f} | edge blend: {args.blend:.2f}")
    print(f"Target: {OUT_W}x{OUT_H}, {OUT_FPS} FPS | FFmpeg log: {log_path}")

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=log_file, text=True, bufsize=1
        )
        assert process.stdout is not None
        last_shown = -1
        for raw_line in process.stdout:
            line = raw_line.strip()
            if line.startswith("out_time_ms="):
                try:
                    elapsed = int(line.split("=", 1)[1]) / 1_000_000
                    percent = min(100, int((elapsed / duration) * 100))
                    if percent != last_shown:
                        print(f"  Progress: {percent}%", end="\r", flush=True)
                        last_shown = percent
                except ValueError:
                    pass
            elif line == "progress=end":
                print("  Progress: 100%          ")
        return_code = process.wait()

    if return_code != 0:
        try:
            error_text = log_path.read_text(encoding="utf-8", errors="replace")[-5000:]
        except OSError:
            error_text = "Could not read FFmpeg log."
        temp_output.unlink(missing_ok=True)
        raise RuntimeError(
            f"FFmpeg failed for {reel.name} (exit code {return_code}).\nLast log lines:\n{error_text}"
        )

    if not temp_output.exists() or temp_output.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg reported success but temporary output is missing/empty: {temp_output}")

    # Only replace prior output after a successful full encode.
    temp_output.replace(output)

    result_probe = run_probe(output)
    video_stream = first_video_stream(result_probe)
    width = video_stream.get("width")
    height = video_stream.get("height")
    fps = video_stream.get("avg_frame_rate", "unknown")
    audio = has_audio(result_probe)
    out_duration = media_duration(result_probe)

    print(f"Created: {output}")
    print(f"Verified: {width}x{height}, average frame rate {fps}, duration {out_duration:.3f}s")
    print(f"Original audio present: {'yes' if audio else 'no'}")
    print(f"Output size: {output.stat().st_size / (1024 * 1024):.2f} MiB")
    if width != OUT_W or height != OUT_H:
        print(f"WARNING: expected {OUT_W}x{OUT_H}, got {width}x{height}.")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process only Reels at least 9 seconds long; auto-fit, blur-fill, add the chroma-keyed watermark, and apply a first-frame cover."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--test", action="store_true", help="Process the first eligible video (minimum 9 seconds).")
    mode.add_argument("--batch", action="store_true", help="Process all supported videos at least 9 seconds long.")

    parser.add_argument("--overlay-width", type=int, default=960,
                        help="Watermark source width in pixels; default 960.")
    parser.add_argument("--overlay-y", type=int, default=-40,
                        help="Watermark y position in pixels; default -40.")
    parser.add_argument("--overlay-x", default="center",
                        help="Overlay x position: 'center' or a pixel number (default: center).")
    parser.add_argument("--key-color", default="auto",
                        help="Key color as 0xRRGGBB, or 'auto' to sample the green background (default: auto).")
    parser.add_argument("--similarity", type=float, default=0.12,
                        help="RGB colorkey tolerance, 0..1; default 0.12 protects gold details.")
    parser.add_argument("--blend", type=float, default=0.02,
                        help="Softness of the transparency edge, 0..1; default 0.02.")
    parser.add_argument("--portrait-tolerance", type=float, default=0.002,
                        help="Aspect-ratio tolerance for treating input as native 9:16; default 0.002.")
    parser.add_argument("--background-blur", type=int, default=22,
                        help="Blur radius for non-9:16 background; default 22.")
    parser.add_argument("--background-brightness", type=float, default=-0.18,
                        help="Background brightness for non-9:16 reels, -1..1; default -0.18.")
    parser.add_argument("--background-saturation", type=float, default=0.82,
                        help="Background saturation for non-9:16 reels, 0..3; default 0.82.")
    parser.add_argument("--crf", type=int, default=18,
                        help="H.264 quality; lower is higher quality (default: 18).")
    parser.add_argument("--preset", default="medium",
                        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
                        help="x264 speed/size preset (default: medium).")
    parser.add_argument("--audio-bitrate", default="192k", help="AAC audio bitrate (default: 192k).")
    parser.add_argument("--force", action="store_true",
                        help="Reprocess and replace existing output files after a successful render.")

    args = parser.parse_args()
    if args.overlay_width <= 0:
        parser.error("--overlay-width must be positive")
    if not 0 <= args.similarity <= 1 or not 0 <= args.blend <= 1:
        parser.error("--similarity and --blend must be between 0 and 1")
    if not 0 <= args.crf <= 51:
        parser.error("--crf must be between 0 and 51")
    if not 0 <= args.portrait_tolerance <= 0.1:
        parser.error("--portrait-tolerance must be between 0 and 0.1")
    if args.background_blur < 0:
        parser.error("--background-blur cannot be negative")
    if not -1 <= args.background_brightness <= 1:
        parser.error("--background-brightness must be between -1 and 1")
    if not 0 <= args.background_saturation <= 3:
        parser.error("--background-saturation must be between 0 and 3")
    if args.overlay_x != "center":
        try:
            int(args.overlay_x)
        except ValueError:
            parser.error("--overlay-x must be 'center' or an integer pixel position")
    if args.key_color != "auto" and not (
        args.key_color.lower().startswith("0x") and len(args.key_color) == 8
    ):
        parser.error("--key-color must be 'auto' or 0xRRGGBB (for example 0x00FF00)")
    return args


def main() -> int:
    args = parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("Error: ffmpeg and ffprobe must be installed and available on PATH.", file=sys.stderr)
        return 2

    try:
        validate_inputs()
        reels = sorted(
            (p for p in REELS_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES),
            key=lambda p: p.name.lower(),
        )
        if not reels:
            raise FileNotFoundError(f"No supported video files found in {REELS_DIR}")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        print(f"Found {len(reels)} supported video(s) in {REELS_DIR}.")
        print(
            f"Minimum duration: {MIN_REEL_DURATION_SECONDS:.1f}s "
            "(shorter videos will be rejected and left unchanged)."
        )

        # Preflight every source before selecting work. This ensures --test
        # chooses the first eligible Reel rather than accidentally selecting a
        # short file, and batch/force modes reject the same inputs consistently.
        eligible: list[tuple[Path, dict[str, Any]]] = []
        rejected_short = 0
        failures: list[tuple[str, str]] = []

        for reel in reels:
            try:
                probe = run_probe(reel)
                first_video_stream(probe)
                duration = media_duration(probe)
                if duration <= 0:
                    raise RuntimeError("Duration could not be verified by ffprobe.")
                if not is_duration_eligible(duration):
                    rejected_short += 1
                    print(
                        f"[REJECTED - TOO SHORT] {reel.name}: {duration:.3f}s "
                        f"(minimum {MIN_REEL_DURATION_SECONDS:.1f}s). Source left unchanged."
                    )
                    continue
                print(f"[ELIGIBLE] {reel.name}: {duration:.3f}s")
                eligible.append((reel, probe))
            except Exception as exc:
                failures.append((reel.name, str(exc)))
                print(
                    f"[REJECTED - CANNOT VERIFY] {reel.name}: {exc}",
                    file=sys.stderr,
                )

        selected = eligible[:1] if args.test else eligible
        print(
            f"\nEligible: {len(eligible)} | Selected for this run: {len(selected)} "
            f"| Rejected (short): {rejected_short} | Cannot verify: "
            f"{len(failures)}"
        )

        completed = 0
        skipped = 0
        for reel, probe in selected:
            try:
                result = process_one(reel, args, base_probe=probe)
                if result is None:
                    skipped += 1
                else:
                    completed += 1
            except Exception as exc:
                failures.append((reel.name, str(exc)))
                print(f"\nERROR processing {reel.name}: {exc}", file=sys.stderr)

        print(
            f"\nFinished: {completed} processed, {skipped} skipped, "
            f"{rejected_short} rejected (under {MIN_REEL_DURATION_SECONDS:.1f}s), "
            f"{len(failures)} failed/unverifiable."
        )
        print(f"Output folder: {OUTPUT_DIR}")
        print(f"Log folder: {LOG_DIR}")
        if failures:
            print("Failures / unverifiable files:")
            for name, message in failures:
                print(f"- {name}: {message.splitlines()[0]}")
            return 1
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
