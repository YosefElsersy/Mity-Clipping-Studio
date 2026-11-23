#!/usr/bin/env bash
# Mity Clipping Studio - colored launcher for the two standalone scripts.
# Expected layout:
#   ~/Mity-Clipping-Studio/instagram-dm/instagram_dm_monitor.py
#   ~/Mity-Clipping-Studio/instagram-dm/.venv/bin/python
#   ~/Mity-Clipping-Studio/video-processing/process_videos.py

set -u

PROJECT_ROOT="${HOME}/Mity-Clipping-Studio"
MONITOR_DIR="${PROJECT_ROOT}/instagram-dm"
VIDEO_DIR="${PROJECT_ROOT}/video-processing"
MONITOR_SCRIPT="${MONITOR_DIR}/instagram_dm_monitor.py"
VIDEO_SCRIPT="${VIDEO_DIR}/process_videos.py"
VENV_PYTHON="${MONITOR_DIR}/.venv/bin/python"

# Use ANSI colors only when stdout is an interactive terminal and NO_COLOR is unset.
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    RESET='\033[0m'
    BOLD='\033[1m'
    DIM='\033[2m'
    CYAN='\033[38;5;45m'
    BLUE='\033[38;5;75m'
    PURPLE='\033[38;5;141m'
    GREEN='\033[38;5;78m'
    YELLOW='\033[38;5;221m'
    RED='\033[38;5;203m'
    WHITE='\033[97m'
else
    RESET='' BOLD='' DIM='' CYAN='' BLUE='' PURPLE='' GREEN='' YELLOW='' RED='' WHITE=''
fi

clear_screen() {
    if [[ -t 1 ]]; then clear; else printf '\n'; fi
}

pause() {
    printf '\n%bPress Enter to return to the menu...%b' "$DIM" "$RESET"
    read -r _ || true
}

header() {
    clear_screen
    printf '\n'
    printf '%b' "$CYAN$BOLD"
    cat <<'BANNER'
  __  __ ___ _____ __   __
 |  \/  |_ _|_   _|\ \ / /
 | |\/| || |  | |   \ V /
 | |  | || |  | |    | |
 |_|  |_|___| |_|    |_|
BANNER
    printf '%b' "$RESET"
    printf '  %bCLIPPING AUTOMATION%b  %bby $mity%b\n' "$WHITE$BOLD" "$RESET" "$PURPLE$BOLD" "$RESET"
    printf '%b────────────────────────────────────────────────────────%b\n' "$BLUE" "$RESET"
    printf '  %bWorkspace:%b %s\n\n' "$DIM" "$RESET" "$PROJECT_ROOT"
}

check_layout() {
    local missing=0
    if [[ ! -f "$MONITOR_SCRIPT" ]]; then
        printf '  %b[!] Missing:%b %s\n' "$RED" "$RESET" "$MONITOR_SCRIPT"
        missing=1
    fi
    if [[ ! -f "$VIDEO_SCRIPT" ]]; then
        printf '  %b[!] Missing:%b %s\n' "$RED" "$RESET" "$VIDEO_SCRIPT"
        missing=1
    fi
    if [[ "$missing" -ne 0 ]]; then
        printf '\n%bCheck that the two scripts are in the expected folders.%b\n' "$YELLOW" "$RESET"
        return 1
    fi
    return 0
}

show_status() {
    printf '  %bSYSTEM CHECK%b\n' "$CYAN$BOLD" "$RESET"
    if [[ -x "$VENV_PYTHON" ]]; then
        printf '  %b[OK]%b Monitor virtual environment found\n' "$GREEN" "$RESET"
    else
        printf '  %b[!!]%b Monitor virtual environment missing\n' "$RED" "$RESET"
    fi
    if command -v google-chrome >/dev/null 2>&1; then
        printf '  %b[OK]%b Google Chrome found\n' "$GREEN" "$RESET"
    else
        printf '  %b[!!]%b Google Chrome not found in PATH\n' "$RED" "$RESET"
    fi
    if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
        printf '  %b[OK]%b FFmpeg and ffprobe found\n' "$GREEN" "$RESET"
    else
        printf '  %b[!!]%b FFmpeg or ffprobe missing\n' "$RED" "$RESET"
    fi
    if grep -Eq '^MIN_REEL_DURATION_SECONDS[[:space:]]*=[[:space:]]*9([.]0)?$' "$VIDEO_SCRIPT"; then
        printf '  %b[OK]%b Video duration filter: only videos >= 9.0 seconds are processed\n' "$GREEN" "$RESET"
    else
        printf '  %b[!!]%b Could not verify the 9-second duration rule in process_videos.py\n' "$RED" "$RESET"
    fi
    if [[ -f "$VIDEO_DIR/input/assets/greenscreen.mp4" && -f "$VIDEO_DIR/input/assets/cover.jpg" ]]; then
        printf '  %b[OK]%b Video assets found\n' "$GREEN" "$RESET"
    else
        printf '  %b[!!]%b Missing greenscreen.mp4 or cover.jpg in video-processing/input/assets\n' "$RED" "$RESET"
    fi
    printf '\n'
}

run_monitor() {
    printf '\n%bStarting Instagram DM Monitor...%b\n' "$CYAN$BOLD" "$RESET"
    if [[ ! -f "$MONITOR_SCRIPT" ]]; then
        printf '%bMonitor script not found:%b %s\n' "$RED" "$RESET" "$MONITOR_SCRIPT"
        return
    fi
    if [[ ! -x "$VENV_PYTHON" ]]; then
        printf '%bVirtual environment not found.%b\n' "$RED" "$RESET"
        printf 'Create it and install dependencies with:\n'
        printf '  cd "%s"\n' "$MONITOR_DIR"
        printf '  python3 -m venv .venv\n'
        printf '  .venv/bin/pip install playwright yt-dlp secretstorage\n'
        return
    fi
    if ! "$VENV_PYTHON" -c 'import playwright, yt_dlp' >/dev/null 2>&1; then
        printf '%bRequired Python packages are missing in the monitor venv.%b\n' "$RED" "$RESET"
        printf 'Run: "%s" -m pip install playwright yt-dlp secretstorage\n' "$VENV_PYTHON"
        return
    fi
    if ! command -v google-chrome >/dev/null 2>&1; then
        printf '%bGoogle Chrome was not found. Install Google Chrome first.%b\n' "$RED" "$RESET"
        return
    fi
    (cd "$MONITOR_DIR" && PYTHONUNBUFFERED=1 "$VENV_PYTHON" "$MONITOR_SCRIPT")
    local rc=$?
    if [[ $rc -eq 0 ]]; then
        printf '\n%bInstagram Monitor exited.%b\n' "$GREEN" "$RESET"
    else
        printf '\n%bInstagram Monitor exited with code %s.%b\n' "$YELLOW" "$rc" "$RESET"
    fi
}

run_video() {
    local mode="$1"
    local description="$2"
    printf '\n%b%s%b\n' "$CYAN$BOLD" "$description" "$RESET"
    if [[ ! -f "$VIDEO_SCRIPT" ]]; then
        printf '%bVideo processor not found:%b %s\n' "$RED" "$RESET" "$VIDEO_SCRIPT"
        return
    fi
    if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
        printf '%bFFmpeg and ffprobe are required. Install them first.%b\n' "$RED" "$RESET"
        return
    fi
    (cd "$VIDEO_DIR" && python3 "$VIDEO_SCRIPT" $mode)
    local rc=$?
    if [[ $rc -eq 0 ]]; then
        printf '\n%bVideo processing command completed.%b\n' "$GREEN" "$RESET"
    else
        printf '\n%bVideo processing exited with code %s.%b\n' "$YELLOW" "$rc" "$RESET"
    fi
}

open_folder() {
    local folder="$1"
    mkdir -p "$folder"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$folder" >/dev/null 2>&1 &
        printf '%bOpened:%b %s\n' "$GREEN" "$RESET" "$folder"
    else
        printf 'Folder: %s\n' "$folder"
    fi
}

if [[ ! -d "$PROJECT_ROOT" ]]; then
    printf '%bProject folder not found:%b %s\n' "$RED" "$RESET" "$PROJECT_ROOT"
    exit 1
fi

while true; do
    header
    show_status
    printf '%bMAIN MENU%b\n\n' "$PURPLE$BOLD" "$RESET"
    printf '  %b[1]%b  Start Instagram DM Monitor\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[2]%b  Process One Eligible Test Video (>=9s)\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[3]%b  Process All Eligible Reels (>=9s)\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[4]%b  Reprocess Eligible Reels (>=9s, Force)\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[5]%b  Open Downloaded Reels Folder\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[6]%b  Open Processed Videos Folder\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[7]%b  Open FFmpeg Logs Folder\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[8]%b  Check Project Files\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[0]%b  Exit\n\n' "$RED$BOLD" "$RESET"
    printf '%bSelect an option:%b ' "$WHITE$BOLD" "$RESET"
    read -r choice || exit 0

    case "$choice" in
        1) header; run_monitor; pause ;;
        2) header; run_video "--test" "Processing one test video"; pause ;;
        3) header; run_video "--batch" "Processing all videos with duration >= 9.0 seconds"; pause ;;
        4)
            header
            printf '%bThis will replace existing outputs only for videos >= 9.0 seconds after successful rendering.%b\n' "$YELLOW" "$RESET"
            printf 'Continue? [y/N]: '
            read -r confirm
            if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
                run_video "--batch --force" "Force reprocessing videos with duration >= 9.0 seconds"
            else
                printf 'Cancelled.\n'
            fi
            pause
            ;;
        5) open_folder "$VIDEO_DIR/input/reels"; pause ;;
        6) open_folder "$VIDEO_DIR/output"; pause ;;
        7) open_folder "$VIDEO_DIR/logs"; pause ;;
        8) header; check_layout || true; show_status; pause ;;
        0) printf '\n%bGoodbye — Clipping Automation by $mity%b\n' "$PURPLE$BOLD" "$RESET"; exit 0 ;;
        *) printf '\n%bInvalid option. Choose one of the listed numbers.%b\n' "$RED" "$RESET"; sleep 1 ;;
    esac
done
