# Mity-Clipping-Studio installer for Windows 10/11 PowerShell.
# Installs Python dependencies into instagram-dm\.venv and offers to install
# Google Chrome and FFmpeg through WinGet after explicit user consent.
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$MonitorDir = Join-Path $ProjectRoot 'instagram-dm'
$VideoDir = Join-Path $ProjectRoot 'video-processing'
$VenvDir = Join-Path $MonitorDir '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$Requirements = Join-Path $ProjectRoot 'requirements.txt'

function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "[ OK ] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "[FAIL] $Message" -ForegroundColor Red }
function Confirm-Install([string]$Message) {
    $answer = Read-Host "$Message [Y/n]"
    return ([string]::IsNullOrWhiteSpace($answer) -or $answer -match '^(y|yes)$')
}
function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machinePath;$userPath"
}
function Test-ChromeInstalled {
    if (Get-Command chrome.exe -ErrorAction SilentlyContinue) { return $true }
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
    ) | Where-Object { $_ -and (Test-Path $_) }
    return ($candidates.Count -gt 0)
}
function Install-WingetPackage([string]$PackageId, [string]$DisplayName) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Warn "WinGet is unavailable; cannot automatically install $DisplayName."
        return $false
    }
    if (-not (Confirm-Install "Install $DisplayName using WinGet ($PackageId)?")) {
        Write-Warn "$DisplayName installation skipped."
        return $false
    }
    Write-Info "Installing $DisplayName..."
    & $winget.Source install --exact --id $PackageId --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "WinGet could not confirm installation of $DisplayName (exit code $LASTEXITCODE)."
        return $false
    }
    Refresh-ProcessPath
    Write-Ok "$DisplayName installation command completed."
    return $true
}

Write-Host ''
Write-Host 'CLIPPING AUTOMATION — BY $mity' -ForegroundColor Cyan
Write-Host 'Windows environment setup' -ForegroundColor DarkGray
Write-Host ''

# Find Python 3.11+ using the Python Launcher first, then python.exe.
$PythonExe = $null
$PythonPrefix = @()
$pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyLauncher) {
    & $pyLauncher.Source -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' *> $null
    if ($LASTEXITCODE -eq 0) {
        $PythonExe = $pyLauncher.Source
        $PythonPrefix = @('-3')
    }
}
if (-not $PythonExe) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        & $pythonCommand.Source --version *> $null
        if ($LASTEXITCODE -eq 0) {
            $versionText = & $pythonCommand.Source -c 'import sys; print("%d.%d" % sys.version_info[:2])'
            $parts = $versionText.Trim().Split('.')
            if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11)) {
                $PythonExe = $pythonCommand.Source
            }
        }
    }
}
if (-not $PythonExe) {
    Write-Warn 'Python 3.11 or newer was not found.'
    $wingetForPython = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($wingetForPython -and (Confirm-Install 'Install Python 3.12 using WinGet?')) {
        Write-Info 'Installing Python 3.12...'
        & $wingetForPython.Source install --exact --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'WinGet could not install Python 3.12.' }
        Refresh-ProcessPath
        $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($pyLauncher) {
            & $pyLauncher.Source -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' *> $null
            if ($LASTEXITCODE -eq 0) { $PythonExe = $pyLauncher.Source; $PythonPrefix = @('-3') }
        }
        if (-not $PythonExe) {
            $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($pythonCommand) {
                & $pythonCommand.Source -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' *> $null
                if ($LASTEXITCODE -eq 0) { $PythonExe = $pythonCommand.Source }
            }
        }
    }
}
if (-not $PythonExe) {
    Write-Fail 'Python 3.11 or newer is required.'
    Write-Host 'Install Python from https://www.python.org/downloads/windows/, reopen PowerShell, and rerun setup.ps1.'
    exit 2
}
$pythonVersion = if ($PythonPrefix.Count) { & $PythonExe @PythonPrefix --version } else { & $PythonExe --version }
Write-Ok "Python: $pythonVersion"

# Create required project directories.
$directories = @(
    $MonitorDir,
    (Join-Path $VideoDir 'input\reels'),
    (Join-Path $VideoDir 'input\staging'),
    (Join-Path $VideoDir 'input\rejected'),
    (Join-Path $VideoDir 'input\assets'),
    (Join-Path $VideoDir 'output'),
    (Join-Path $VideoDir 'logs')
)
foreach ($directory in $directories) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
Write-Ok 'Project directories created.'

# Create the local virtual environment.
if (-not (Test-Path $VenvPython)) {
    Write-Info 'Creating Instagram monitor virtual environment...'
    if ($PythonPrefix.Count) {
        & $PythonExe @PythonPrefix -m venv $VenvDir
    } else {
        & $PythonExe -m venv $VenvDir
    }
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
if (-not (Test-Path $VenvPython)) { throw "Virtual environment Python was not created: $VenvPython" }

Write-Info 'Upgrading pip...'
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
Write-Info 'Installing Python packages from requirements.txt...'
& $VenvPython -m pip install -r $Requirements
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Write-Ok 'Python dependencies installed.'

# System dependencies. The installer asks before using WinGet.
if (-not (Test-ChromeInstalled)) {
    [void](Install-WingetPackage 'Google.Chrome' 'Google Chrome Stable')
} else {
    Write-Ok 'Google Chrome detected.'
}
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
    [void](Install-WingetPackage 'Gyan.FFmpeg' 'FFmpeg and ffprobe')
} else {
    Write-Ok 'FFmpeg and ffprobe detected.'
}
Refresh-ProcessPath

if (Test-ChromeInstalled) { Write-Ok 'Google Chrome is available.' }
else { Write-Warn 'Google Chrome is missing. Instagram monitoring requires Google Chrome Stable.' }
if ((Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -and (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
    Write-Ok 'FFmpeg and ffprobe are available.'
} else {
    Write-Warn 'FFmpeg/ffprobe are missing. Install them or reopen PowerShell after WinGet completes.'
}

$overlay = Join-Path $VideoDir 'input\assets\greenscreen.mp4'
$cover = Join-Path $VideoDir 'input\assets\cover.jpg'
if ((Test-Path $overlay) -and (Test-Path $cover)) {
    Write-Ok 'Required video assets found.'
} else {
    Write-Warn 'Add your own assets before processing:'
    Write-Host "  $overlay"
    Write-Host "  $cover"
}

Write-Host ''
Write-Ok 'Setup finished.'
Write-Host "Next: .\run.ps1" -ForegroundColor Cyan
Write-Host 'The dedicated Chrome profile will be stored under %LOCALAPPDATA%\Mity-Clipping-Studio\instagram-dm\chrome-profile.'
Write-Host 'If WinGet changed PATH, close and reopen PowerShell before running the application.'
