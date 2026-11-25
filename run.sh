#!/usr/bin/env bash
# Colored Linux launcher for the independent Mity-Clipping-Studio tools.
set -u
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_DIR="$PROJECT_ROOT/instagram-dm"
VIDEO_DIR="$PROJECT_ROOT/video-processing"
MONITOR_SCRIPT="$MONITOR_DIR/instagram_dm_monitor.py"
VIDEO_SCRIPT="$VIDEO_DIR/process_videos.py"
RENAME_SCRIPT="$PROJECT_ROOT/rename_videos.py"
VENV_PYTHON="$MONITOR_DIR/.venv/bin/python"
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    RESET='\033[0m'; BOLD='\033[1m'; DIM='\033[2m'
    CYAN='\033[38;5;45m'; BLUE='\033[38;5;75m'; PURPLE='\033[38;5;141m'
    GREEN='\033[38;5;78m'; YELLOW='\033[38;5;221m'; RED='\033[38;5;203m'; WHITE='\033[97m'
else
    RESET=''; BOLD=''; DIM=''; CYAN=''; BLUE=''; PURPLE=''; GREEN=''; YELLOW=''; RED=''; WHITE=''
fi
clear_screen() { if [[ -t 1 ]]; then clear; else printf '\n'; fi; }
pause() { printf '\n%bPress Enter to return to the menu...%b' "$DIM" "$RESET"; read -r _ || true; }
header() {
    clear_screen
    printf '\n%b' "$CYAN$BOLD"
    cat <<'BANNER'
  __  __ ___ _____ __   __
 |  \/  |_ _|_   _|\ \ / /
 | |\/| || |  | |  \ V /
 | |  | || |  | |   | |
 |_|  |_|___| |_|   |_|
BANNER
    printf '%b' "$RESET"
    printf '  %bCLIPPING AUTOMATION%b  %bby $mity%b\n' "$WHITE$BOLD" "$RESET" "$PURPLE$BOLD" "$RESET"
    printf '%b────────────────────────────────────────────────────────%b\n' "$BLUE" "$RESET"
    printf '  %bWorkspace:%b %s\n\n' "$DIM" "$RESET" "$PROJECT_ROOT"
}
check_layout() {
    local missing=0
    for file in "$MONITOR_SCRIPT" "$VIDEO_SCRIPT" "$RENAME_SCRIPT"; do
        if [[ ! -f "$file" ]]; then
            printf '  %b[!] Missing:%b %s\n' "$RED" "$RESET" "$file"
            missing=1
        fi
    done
    if [[ "$missing" -ne 0 ]]; then
        printf '\n%bCheck the project folder structure.%b\n' "$YELLOW" "$RESET"
        return 1
    fi
    return 0
}
chrome_found() {
    command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1
}
show_status() {
    printf '  %bSYSTEM CHECK%b\n' "$CYAN$BOLD" "$RESET"
    if [[ -x "$VENV_PYTHON" ]]; then printf '  %b[OK]%b Monitor virtual environment found\n' "$GREEN" "$RESET"
    else printf '  %b[!!]%b Virtual environment missing — run ./setup.sh\n' "$RED" "$RESET"; fi
    if chrome_found; then printf '  %b[OK]%b Google Chrome found\n' "$GREEN" "$RESET"
    else printf '  %b[!!]%b Google Chrome not found\n' "$RED" "$RESET"; fi
    if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
        printf '  %b[OK]%b FFmpeg and ffprobe found\n' "$GREEN" "$RESET"
    else printf '  %b[!!]%b FFmpeg or ffprobe missing\n' "$RED" "$RESET"; fi
    if [[ -f "$VIDEO_DIR/input/assets/greenscreen.mp4" && -f "$VIDEO_DIR/input/assets/cover.jpg" && -f "$VIDEO_DIR/input/assets/watermark.png" ]]; then
        printf '  %b[OK]%b Video assets found (including watermark.png)\n' "$GREEN" "$RESET"
    else
        printf '  %b[!!]%b Add greenscreen.mp4, cover.jpg and watermark.png to video-processing/input/assets\n' "$YELLOW" "$RESET"
    fi
    if grep -Eq '^MIN_REEL_DURATION_SECONDS[[:space:]]*=[[:space:]]*9([.]0)?$' "$VIDEO_SCRIPT"; then
        printf '  %b[OK]%b Minimum duration: videos >= 9.0 seconds\n' "$GREEN" "$RESET"
    else printf '  %b[!!]%b Could not verify the 9-second duration rule\n' "$YELLOW" "$RESET"; fi
    printf '\n'
}
run_monitor() {
    printf '\n%bStarting Instagram DM Monitor...%b\n' "$CYAN$BOLD" "$RESET"
    if [[ ! -x "$VENV_PYTHON" ]]; then printf '%bRun ./setup.sh first.%b\n' "$RED" "$RESET"; return; fi
    if ! "$VENV_PYTHON" -c 'import playwright, yt_dlp, secretstorage' >/dev/null 2>&1; then
        printf '%bRequired Python packages are missing. Run ./setup.sh.%b\n' "$RED" "$RESET"; return
    fi
    if ! chrome_found; then printf '%bInstall Google Chrome Stable first (./setup.sh can help).%b\n' "$RED" "$RESET"; return; fi
    (cd "$MONITOR_DIR" && PYTHONUNBUFFERED=1 "$VENV_PYTHON" "$MONITOR_SCRIPT")
    local rc=$?
    if [[ $rc -eq 0 ]]; then printf '\n%bInstagram Monitor exited.%b\n' "$GREEN" "$RESET"
    else printf '\n%bInstagram Monitor exited with code %s.%b\n' "$YELLOW" "$rc" "$RESET"; fi
}
run_video() {
    local description="$1"; shift
    printf '\n%b%s%b\n' "$CYAN$BOLD" "$description" "$RESET"
    if [[ ! -f "$VIDEO_SCRIPT" ]]; then printf '%bVideo processor not found.%b\n' "$RED" "$RESET"; return; fi
    if [[ ! -x "$VENV_PYTHON" ]]; then printf '%bRun ./setup.sh first to create the project environment.%b\n' "$RED" "$RESET"; return; fi
    if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
        printf '%bFFmpeg and ffprobe are required. Run ./setup.sh or install them manually.%b\n' "$RED" "$RESET"; return
    fi
    (cd "$VIDEO_DIR" && "$VENV_PYTHON" "$VIDEO_SCRIPT" "$@")
    local rc=$?
    if [[ $rc -eq 0 ]]; then printf '\n%bVideo processing command completed.%b\n' "$GREEN" "$RESET"
    else printf '\n%bVideo processing exited with code %s.%b\n' "$YELLOW" "$rc" "$RESET"; fi
}
run_rename() {
    printf '\n%bPrepare upload numbering%b\n' "$CYAN$BOLD" "$RESET"
    if [[ ! -f "$RENAME_SCRIPT" ]]; then printf '%bRename script not found.%b\n' "$RED" "$RESET"; return; fi
    if [[ ! -x "$VENV_PYTHON" ]]; then printf '%bRun ./setup.sh first to create the project environment.%b\n' "$RED" "$RESET"; return; fi
    "$VENV_PYTHON" "$RENAME_SCRIPT"
    local rc=$?
    if [[ $rc -eq 0 ]]; then printf '\n%bRename tool finished.%b\n' "$GREEN" "$RESET"
    else printf '\n%bRename tool exited with code %s.%b\n' "$YELLOW" "$rc" "$RESET"; fi
}
open_folder() {
    local folder="$1"
    mkdir -p "$folder"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$folder" >/dev/null 2>&1 &
        printf '%bOpened:%b %s\n' "$GREEN" "$RESET" "$folder"
    else printf 'Folder: %s\n' "$folder"; fi
}

if ! check_layout; then exit 1; fi
if [[ ! -x "$VENV_PYTHON" ]] || ! "$VENV_PYTHON" -c 'import playwright, yt_dlp, secretstorage' >/dev/null 2>&1; then
    if [[ "${MITY_SKIP_AUTO_SETUP:-0}" != "1" ]]; then
        printf '%bFirst-time setup is required (Python packages and system checks).%b\n' "$YELLOW" "$RESET"
        printf 'Run setup now? [Y/n]: '
        read -r setup_choice || setup_choice="n"
        if [[ -z "$setup_choice" || "$setup_choice" == "y" || "$setup_choice" == "Y" ]]; then
            bash "$PROJECT_ROOT/setup.sh" || exit $?
        else
            printf '%bSetup skipped. Run ./setup.sh before launching the tools.%b\n' "$YELLOW" "$RESET"
            exit 1
        fi
    else
        printf '%bVirtual environment/dependencies missing. Run ./setup.sh.%b\n' "$RED" "$RESET"
        exit 1
    fi
fi
if [[ ! -x "$VENV_PYTHON" ]] || ! "$VENV_PYTHON" -c 'import playwright, yt_dlp, secretstorage' >/dev/null 2>&1; then
    printf '%bSetup did not complete the required Python environment.%b\n' "$RED" "$RESET"
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
    printf '  %b[9]%b  Rename Output + Rejected Videos for Upload\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[10]%b Open Rejected Videos Folder\n' "$CYAN$BOLD" "$RESET"
    printf '  %b[0]%b  Exit\n\n' "$RED$BOLD" "$RESET"
    printf '%bSelect an option:%b ' "$WHITE$BOLD" "$RESET"
    read -r choice || exit 0
    case "$choice" in
        1) header; run_monitor; pause ;;
        2) header; run_video "Processing one eligible test video" --test; pause ;;
        3) header; run_video "Processing all videos with duration >= 9.0 seconds" --batch; pause ;;
        4)
            header
            printf '%bExisting outputs will be replaced only after a successful render. Short videos will be moved to input/rejected.%b\n' "$YELLOW" "$RESET"
            printf 'Continue? [y/N]: '
            read -r confirm
            if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
                run_video "Force reprocessing eligible videos" --batch --force
            else printf 'Cancelled.\n'; fi
            pause
            ;;
        5) open_folder "$VIDEO_DIR/input/reels"; pause ;;
        6) open_folder "$VIDEO_DIR/output"; pause ;;
        7) open_folder "$VIDEO_DIR/logs"; pause ;;
        8) header; check_layout || true; show_status; pause ;;
        9) header; run_rename; pause ;;
        10) open_folder "$VIDEO_DIR/input/rejected"; pause ;;
        0) printf '\n%bGoodbye — Clipping Automation by $mity%b\n' "$PURPLE$BOLD" "$RESET"; exit 0 ;;
        *) printf '\n%bInvalid option. Choose one of the listed numbers.%b\n' "$RED" "$RESET"; sleep 1 ;;
    esac
done
