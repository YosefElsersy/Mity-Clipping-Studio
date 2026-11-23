#!/usr/bin/env bash
# Cross-platform-aware installer for Linux (Ubuntu/Debian) environments.
# It installs Python packages into instagram-dm/.venv and offers to install
# system dependencies only after explicit user consent.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_DIR="$ROOT/instagram-dm"
VIDEO_DIR="$ROOT/video-processing"
VENV_DIR="$MONITOR_DIR/.venv"
REQUIREMENTS="$ROOT/requirements.txt"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_RESET='\033[0m'; C_CYAN='\033[38;5;45m'; C_GREEN='\033[38;5;78m'
  C_YELLOW='\033[38;5;221m'; C_RED='\033[38;5;203m'; C_BOLD='\033[1m'
else
  C_RESET=''; C_CYAN=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_BOLD=''
fi

info() { printf '%b[INFO]%b %s\n' "$C_CYAN" "$C_RESET" "$*"; }
success() { printf '%b[ OK ]%b %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%b[WARN]%b %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
error() { printf '%b[FAIL]%b %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
ask_yes() {
  local answer
  read -r -p "$1 [Y/n]: " answer || answer="n"
  [[ -z "$answer" || "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

on_error() {
  local code=$?
  error "Setup stopped at line ${BASH_LINENO[0]} (exit code $code)."
  exit "$code"
}
trap on_error ERR

if [[ "$(uname -s)" != "Linux" ]]; then
  error "setup.sh supports Linux only. On Windows, run: .\\setup.ps1"
  exit 2
fi

printf '\n%bCLIPPING AUTOMATION — BY $mity%b\n' "$C_CYAN$C_BOLD" "$C_RESET"
printf 'Linux environment setup\n\n'

# Select Python 3.11+ (current yt-dlp releases require a modern Python runtime).
PYTHON_CMD=""
for candidate in python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PYTHON_CMD="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_CMD" ]]; then
  warn "Python 3.11 or newer was not found."
  if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1 && ask_yes "Install the distribution Python, venv, and pip packages using apt?"; then
    sudo -v
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
    for candidate in python3.12 python3.11 python3 python; do
      if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        PYTHON_CMD="$candidate"
        break
      fi
    done
  fi
fi
if [[ -z "$PYTHON_CMD" ]]; then
  error "Python 3.11 or newer is required. Install it using your Linux distribution's supported package source, then rerun setup.sh."
  exit 3
fi
success "Python: $($PYTHON_CMD --version)"

# Create project folders. User-provided assets are not downloaded automatically.
mkdir -p \
  "$MONITOR_DIR" \
  "$VIDEO_DIR/input/reels" \
  "$VIDEO_DIR/input/staging" \
  "$VIDEO_DIR/input/rejected" \
  "$VIDEO_DIR/input/assets" \
  "$VIDEO_DIR/output" \
  "$VIDEO_DIR/logs"
success "Project directories created."

# Offer installation of system dependencies on Debian/Ubuntu.
missing_system=()
PYTHON_VENV_PACKAGE="$($PYTHON_CMD -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}-venv")')"
"$PYTHON_CMD" -c 'import venv, ensurepip' >/dev/null 2>&1 || missing_system+=("Python venv support")
command -v ffmpeg >/dev/null 2>&1 || missing_system+=("FFmpeg/ffprobe")
(command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1) || missing_system+=("Google Chrome Stable")

if ((${#missing_system[@]})); then
  warn "Missing system dependencies: ${missing_system[*]}"
  if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    if ask_yes "Install missing system dependencies using apt and sudo?"; then
      sudo -v
      sudo apt-get update
      if [[ " ${missing_system[*]} " == *" Python venv support "* ]]; then
        info "Installing Python virtual environment support..."
        sudo apt-get install -y "$PYTHON_VENV_PACKAGE" python3-venv python3-pip
      fi
      if [[ " ${missing_system[*]} " == *" FFmpeg/ffprobe "* ]]; then
        info "Installing FFmpeg and ffprobe..."
        sudo apt-get install -y ffmpeg
      fi
      if [[ " ${missing_system[*]} " == *" Google Chrome Stable "* ]]; then
        if [[ "$(uname -m)" != "x86_64" ]]; then
          warn "The official Google Chrome .deb installer is for supported x86_64 Linux systems. Install Chrome manually for this architecture."
        else
          info "Downloading the official Google Chrome Stable .deb package..."
          tmp_dir="$(mktemp -d)"
          trap 'rm -rf "${tmp_dir:-}"' EXIT
          deb_file="$tmp_dir/google-chrome-stable_current_amd64.deb"
          if command -v curl >/dev/null 2>&1; then
            curl -fL --retry 3 -o "$deb_file" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
          elif command -v wget >/dev/null 2>&1; then
            wget -O "$deb_file" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
          else
            error "curl or wget is required to download Google Chrome."
            exit 4
          fi
          sudo apt-get install -y "$deb_file"
          rm -rf "$tmp_dir"
          trap on_error ERR
        fi
      fi
    else
      warn "System dependency installation was skipped by the user."
    fi
  else
    warn "Automatic system installation is unavailable (apt-get/sudo not found). Install the missing tools manually."
  fi
fi

# Create/use the monitor's virtual environment.
if ! "$PYTHON_CMD" -c 'import venv, ensurepip' >/dev/null 2>&1; then
  error "Python venv support is unavailable. Install the matching pythonX.Y-venv package and rerun setup.sh."
  exit 5
fi
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  info "Creating Instagram monitor virtual environment..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi
VENV_PYTHON="$VENV_DIR/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  error "Virtual environment creation failed. On Ubuntu/Debian, install python3-venv and retry."
  exit 5
fi

info "Upgrading pip..."
"$VENV_PYTHON" -m pip install --upgrade pip
info "Installing Python dependencies from requirements.txt..."
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS"
success "Python dependencies installed in $VENV_DIR"

# The monitor launches the installed, branded Chrome via Playwright channel='chrome'.
# Do not download a separate Playwright Chromium build for this project.
if command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1; then
  success "Google Chrome detected. Playwright will use the installed Chrome channel."
else
  warn "Google Chrome is still missing. Instagram monitoring will not start until Chrome Stable is installed."
fi
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  success "FFmpeg and ffprobe detected."
else
  warn "FFmpeg/ffprobe are still missing. Video processing will not start until they are installed."
fi

if [[ -f "$VIDEO_DIR/input/assets/greenscreen.mp4" && -f "$VIDEO_DIR/input/assets/cover.jpg" ]]; then
  success "Required video assets found."
else
  warn "Add your own assets before processing:"
  printf '  %s\n' "$VIDEO_DIR/input/assets/greenscreen.mp4" "$VIDEO_DIR/input/assets/cover.jpg"
fi

printf '\n%bSetup finished.%b\n' "$C_GREEN$C_BOLD" "$C_RESET"
printf 'Next: cd "%s" && ./run.sh\n' "$ROOT"
printf 'The Chrome profile is stored outside the repository; existing Linux profile: ~/.local/share/instagram-dm/chrome-profile\n'
