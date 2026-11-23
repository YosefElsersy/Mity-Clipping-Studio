# Colored Windows launcher for Mity-Clipping-Studio.
$ErrorActionPreference = 'Continue'
$ProjectRoot = $PSScriptRoot
$MonitorDir = Join-Path $ProjectRoot 'instagram-dm'
$VideoDir = Join-Path $ProjectRoot 'video-processing'
$MonitorScript = Join-Path $MonitorDir 'instagram_dm_monitor.py'
$VideoScript = Join-Path $VideoDir 'process_videos.py'
$VenvPython = Join-Path $MonitorDir '.venv\Scripts\python.exe'

function Write-Info([string]$Message) { Write-Host $Message -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host $Message -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host $Message -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host $Message -ForegroundColor Red }
function Pause-Menu { Write-Host ''; [void](Read-Host 'Press Enter to return to the menu') }
function Test-ChromeInstalled {
    if (Get-Command chrome.exe -ErrorAction SilentlyContinue) { return $true }
    $paths = @(
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
    ) | Where-Object { $_ -and (Test-Path $_) }
    return ($paths.Count -gt 0)
}
function Show-Header {
    Clear-Host
    Write-Host ''
    Write-Host '  __  __ ___ _____ __   __' -ForegroundColor Cyan
    Write-Host ' |  \/  |_ _|_   _|\ \ / /' -ForegroundColor Cyan
    Write-Host ' | |\/| || |  | |  \ V /' -ForegroundColor Blue
    Write-Host ' | |  | || |  | |   | |' -ForegroundColor Blue
    Write-Host ' |_|  |_|___| |_|   |_|' -ForegroundColor Magenta
    Write-Host ''
    Write-Host '  CLIPPING AUTOMATION' -ForegroundColor White -NoNewline
    Write-Host '  by $mity' -ForegroundColor Magenta
    Write-Host '  ────────────────────────────────────────────────────────' -ForegroundColor DarkCyan
    Write-Host "  Workspace: $ProjectRoot" -ForegroundColor DarkGray
    Write-Host ''
}
function Show-Status {
    Write-Host '  SYSTEM CHECK' -ForegroundColor Cyan
    if (Test-Path $VenvPython) { Write-Ok '  [OK] Monitor virtual environment found' }
    else { Write-Fail '  [!!] Virtual environment missing — run .\setup.ps1' }
    if (Test-ChromeInstalled) { Write-Ok '  [OK] Google Chrome found' }
    else { Write-Fail '  [!!] Google Chrome not found' }
    if ((Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -and (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) { Write-Ok '  [OK] FFmpeg and ffprobe found' }
    else { Write-Fail '  [!!] FFmpeg or ffprobe missing' }
    if ((Test-Path (Join-Path $VideoDir 'input\assets\greenscreen.mp4')) -and (Test-Path (Join-Path $VideoDir 'input\assets\cover.jpg'))) { Write-Ok '  [OK] Video assets found' }
    else { Write-Warn '  [!!] Missing greenscreen.mp4 or cover.jpg in video-processing\input\assets' }
    if (Test-Path $VideoDir) { Write-Ok '  [OK] Video project directory found' }
    if (Select-String -Path $VideoScript -Pattern '^MIN_REEL_DURATION_SECONDS\s*=\s*9(\.0)?$' -Quiet -ErrorAction SilentlyContinue) { Write-Ok '  [OK] Minimum duration filter: videos >= 9 seconds' }
    else { Write-Warn '  [!!] Could not verify the 9-second duration rule' }
    Write-Host ''
}
function Invoke-Monitor {
    if (-not (Test-Path $MonitorScript)) { Write-Fail "Monitor script not found: $MonitorScript"; return }
    if (-not (Test-Path $VenvPython)) { Write-Fail 'Virtual environment is missing. Run .\setup.ps1 first.'; return }
    & $VenvPython -c 'import playwright, yt_dlp' *> $null
    if ($LASTEXITCODE -ne 0) { Write-Fail 'Required Python packages are missing. Run .\setup.ps1.'; return }
    if (-not (Test-ChromeInstalled)) { Write-Fail 'Google Chrome Stable is required. Run .\setup.ps1.'; return }
    Write-Info 'Starting Instagram DM Monitor...'
    Push-Location $MonitorDir
    try { & $VenvPython $MonitorScript; $code = $LASTEXITCODE }
    finally { Pop-Location }
    if ($code -eq 0) { Write-Ok 'Instagram Monitor exited.' }
    else { Write-Warn "Instagram Monitor exited with code $code." }
}
function Invoke-Video([string[]]$Arguments, [string]$Description) {
    if (-not (Test-Path $VideoScript)) { Write-Fail "Video processor not found: $VideoScript"; return }
    if (-not (Test-Path $VenvPython)) { Write-Fail 'Virtual environment is missing. Run .\setup.ps1 first.'; return }
    if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
        Write-Fail 'FFmpeg and ffprobe are required. Run .\setup.ps1 or install FFmpeg.'; return
    }
    Write-Info $Description
    Push-Location $VideoDir
    try { & $VenvPython $VideoScript @Arguments; $code = $LASTEXITCODE }
    finally { Pop-Location }
    if ($code -eq 0) { Write-Ok 'Video processing command completed.' }
    else { Write-Warn "Video processing exited with code $code." }
}
function Open-Folder([string]$Folder) {
    New-Item -ItemType Directory -Force -Path $Folder | Out-Null
    if (Get-Command explorer.exe -ErrorAction SilentlyContinue) { Start-Process -FilePath explorer.exe -ArgumentList ('"{0}"' -f $Folder) }
    else { Write-Host "Folder: $Folder" }
}

if (-not (Test-Path $MonitorScript) -or -not (Test-Path $VideoScript)) {
    Write-Fail 'One or more project scripts are missing. Check the repository folder structure.'
    exit 1
}

# First-run convenience: invoke the platform installer when the virtual
# environment or required Python packages are missing.
$needsSetup = -not (Test-Path $VenvPython)
if (-not $needsSetup) {
    & $VenvPython -c 'import playwright, yt_dlp' *> $null
    $needsSetup = ($LASTEXITCODE -ne 0)
}
if ($needsSetup) {
    if ($env:MITY_SKIP_AUTO_SETUP -eq '1') {
        Write-Fail 'The Python environment is missing. Run .\setup.ps1 first.'
        exit 1
    }
    Write-Warn 'First-time setup is required (Python packages and system checks).'
    $setupChoice = Read-Host 'Run setup now? [Y/n]'
    if ([string]::IsNullOrWhiteSpace($setupChoice) -or $setupChoice -match '^(y|yes)$') {
        & (Join-Path $ProjectRoot 'setup.ps1')
        if (-not (Test-Path $VenvPython)) {
            Write-Fail 'Setup did not create the virtual environment. Review the setup output and retry.'
            exit 1
        }
        & $VenvPython -c 'import playwright, yt_dlp' *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Fail 'Python dependencies are still missing. Run .\setup.ps1 and review the errors.'
            exit 1
        }
    } else {
        Write-Warn 'Setup skipped. Run .\setup.ps1 before launching the tools.'
        exit 1
    }
}

while ($true) {
    Show-Header
    Show-Status
    Write-Host '  MAIN MENU' -ForegroundColor Magenta
    Write-Host ''
    Write-Host '  [1]  Start Instagram DM Monitor' -ForegroundColor Cyan
    Write-Host '  [2]  Process One Eligible Test Video (>=9s)' -ForegroundColor Cyan
    Write-Host '  [3]  Process All Eligible Reels (>=9s)' -ForegroundColor Cyan
    Write-Host '  [4]  Reprocess Eligible Reels (>=9s, Force)' -ForegroundColor Cyan
    Write-Host '  [5]  Open Downloaded Reels Folder' -ForegroundColor Cyan
    Write-Host '  [6]  Open Processed Videos Folder' -ForegroundColor Cyan
    Write-Host '  [7]  Open FFmpeg Logs Folder' -ForegroundColor Cyan
    Write-Host '  [8]  Check Project Files' -ForegroundColor Cyan
    Write-Host '  [0]  Exit' -ForegroundColor Red
    Write-Host ''
    $choice = Read-Host '  Select an option'
    switch ($choice) {
        '1' { Show-Header; Invoke-Monitor; Pause-Menu }
        '2' { Show-Header; Invoke-Video -Arguments @('--test') -Description 'Processing one eligible test video'; Pause-Menu }
        '3' { Show-Header; Invoke-Video -Arguments @('--batch') -Description 'Processing all videos with duration >= 9.0 seconds'; Pause-Menu }
        '4' {
            Show-Header
            Write-Warn 'This replaces existing outputs only after successful rendering and only for videos >= 9 seconds.'
            $confirm = Read-Host 'Continue? [y/N]'
            if ($confirm -match '^(y|yes)$') { Invoke-Video -Arguments @('--batch', '--force') -Description 'Force reprocessing eligible videos' }
            else { Write-Host 'Cancelled.' }
            Pause-Menu
        }
        '5' { Open-Folder (Join-Path $VideoDir 'input\reels'); Pause-Menu }
        '6' { Open-Folder (Join-Path $VideoDir 'output'); Pause-Menu }
        '7' { Open-Folder (Join-Path $VideoDir 'logs'); Pause-Menu }
        '8' { Show-Header; Show-Status; Pause-Menu }
        '0' { Write-Host ''; Write-Host 'Goodbye — Clipping Automation by $mity' -ForegroundColor Magenta; exit 0 }
        default { Write-Warn 'Invalid option. Choose one of the listed numbers.'; Start-Sleep -Seconds 1 }
    }
}
