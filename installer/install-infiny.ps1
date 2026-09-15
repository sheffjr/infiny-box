<#
Infiny Box - one-file installer.

ASCII ONLY, English only. Two reasons, both learned the hard way:
  * cmd.exe reads .bat in the console OEM codepage and PowerShell 5.1 reads .ps1
    as ANSI unless the file carries a UTF-8 BOM. Non-ASCII text in either one
    turns into mojibake, and in the .bat case fragments of mangled lines get
    executed as commands. Staying inside ASCII removes the whole class of bug.
  * English is the product default (see README and infiny_cli/i18n.py). A
    Russian-only installer in front of an English product is just inconsistent.

Administrator rights are NOT required when WSL2 is already enabled - which is
the common case. `wsl --import` runs fine as a normal user; elevation is needed
only to turn the WSL2 platform on for the first time.

Parameters (for automated testing; a human needs neither):
  -InstallDir <path>   install here, no prompt
  -NoPause             do not wait for Enter at the end
#>
param(
    [string]$InstallDir,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$WslFile     = Join-Path $PSScriptRoot "infiny.wsl"
$DistroName  = "Infiny"
$DefaultDir  = "$env:LOCALAPPDATA\Infiny"

function Write-Step($msg) { Write-Host "-> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[ok] $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "[!!] $msg" -ForegroundColor Red }
function Pause-Exit($code) {
    if (-not $NoPause) { Read-Host "Press Enter to exit" }
    exit $code
}

# Run a native command without letting its stderr become a terminating error.
#
# This is not defensive style, it is a fix for a real crash. With
# $ErrorActionPreference = "Stop", PowerShell converts anything a native
# program writes to stderr into an ErrorRecord and throws. `wsl --status` on a
# machine where WSL is not installed writes exactly such a message - so the
# installer died precisely in the situation it exists to handle, before
# printing a single useful line.
function Invoke-Native {
    param([scriptblock]$Command)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try { & $Command 2>&1 | Out-Null; return $LASTEXITCODE }
    finally { $ErrorActionPreference = $prev }
}

Write-Host ""
Write-Host "  +==========================================+" -ForegroundColor Yellow
Write-Host "  |   Infiny Box - an AI terminal, sandboxed  |" -ForegroundColor Yellow
Write-Host "  +==========================================+" -ForegroundColor Yellow
Write-Host ""

# --- Step 1: WSL2 platform ---------------------------------------------------
Write-Step "Checking the WSL2 platform..."
$wslRc = Invoke-Native { wsl --status }

if ($wslRc -ne 0) {
    $isAdmin = (New-Object Security.Principal.WindowsPrincipal(
        [Security.Principal.WindowsIdentity]::GetCurrent())
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    if (-not $isAdmin) {
        Write-Err "WSL2 is not enabled, and enabling it needs administrator rights."
        Write-Host "  Right-click install-infiny.bat -> 'Run as administrator'," -ForegroundColor Yellow
        Write-Host "  then run it again." -ForegroundColor Yellow
        Pause-Exit 1
    }

    Write-Step "WSL2 is not enabled yet - enabling it (one time)..."
    $rc = Invoke-Native { wsl --install --no-distribution }
    if ($rc -ne 0) {
        Write-Err "Could not enable WSL2 automatically (exit code $rc)."
        Write-Host "  Try manually:  wsl --install" -ForegroundColor Yellow
        Pause-Exit 1
    }
    Write-Ok "WSL2 enabled."
    Write-Host ""
    Write-Host "  ONE reboot is required to finish enabling the platform." -ForegroundColor Yellow
    Write-Host "  Run this installer again afterwards - it continues from here." -ForegroundColor Yellow
    Write-Host ""
    if (-not $NoPause) {
        if ((Read-Host "  Reboot now? (y/n)") -eq "y") { Restart-Computer -Force }
    }
    exit 0
}
Write-Ok "WSL2 is enabled."

if (-not (Test-Path $WslFile)) {
    Write-Err "infiny.wsl was not found next to this installer."
    Write-Host "  install-infiny.bat and infiny.wsl must sit in the same folder." -ForegroundColor Yellow
    Pause-Exit 1
}

# --- Step 2: where to install ------------------------------------------------
# We ask on purpose. `wsl --install --from-file` only ever unpacks to the system
# drive with no choice, and the Box takes about 2 GB unpacked. Silently eating
# that much space on a full C: is a bad first impression.
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    Write-Host ""
    Write-Host "  The Box needs about 2 GB unpacked." -ForegroundColor White
    Write-Host "  Default: $DefaultDir" -ForegroundColor Gray
    $InstallDir = Read-Host "  Install where? (Enter for default)"
    if ([string]::IsNullOrWhiteSpace($InstallDir)) { $InstallDir = $DefaultDir }
}

$drive = Split-Path $InstallDir -Qualifier
if ($drive) {
    $free = (Get-PSDrive $drive.TrimEnd(':') -ErrorAction SilentlyContinue).Free
    if ($free -and $free -lt 4GB) {
        Write-Err ("Drive {0} has only {1:N1} GB free - not enough." -f $drive, ($free/1GB))
        Write-Host "  Pick another drive and run the installer again." -ForegroundColor Yellow
        Pause-Exit 1
    }
}

# --- Step 3: remove any previous install -------------------------------------
# This runs BEFORE the non-empty check below, and the order is the whole point.
#
# It used to be the other way round, which made reinstalling impossible. A
# previous install leaves ext4.vhdx in the target directory, so the non-empty
# check fired first, printed "choose an empty directory" and exited - control
# never reached this block at all. Reinstalling into the same directory was
# therefore permanently broken, and it is the single most likely thing a user
# does after a new version comes out.
#
# Unregistering first also empties the directory, so the check below then
# passes honestly rather than being weakened to accommodate us.
#
# WSL_UTF8: `wsl -l -q` emits UTF-16LE, and Windows PowerShell 5.1 - which
# install-infiny.bat launches - decodes native output using the console
# encoding. The result is a string with a NUL between every character, so
# "^Infiny$" never matched and an existing distro was never detected. Measured
# on 2026-09-03: char codes came back as 100 0 111 0 99 0 for "doc...".
# `wsl --import` then failed with "distribution already exists". One variable
# fixes it, and it is harmless everywhere else.
$env:WSL_UTF8 = 1
$existing = wsl -l -q 2>&1 | Select-String -Pattern "^$DistroName$"
if ($existing) {
    Write-Step "Infiny is already installed - removing the old copy..."
    Invoke-Native { wsl --unregister $DistroName } | Out-Null
}

# Refuse a non-empty directory. This is safety, not tidiness: uninstalling
# removes the install directory, so dropping the Box next to unrelated files
# means the uninstaller would take them too. Seen for real - a folder here held
# two ISOs and a 2 GB model from earlier versions of this project.
#
# Files this installer put there itself do not count. It writes
# uninstall-infiny.bat into the install directory, and `wsl --unregister`
# removes the virtual disk but not that file - so a second install found one
# leftover item and refused, which made reinstalling over an existing Box
# impossible. The upgrade path was broken by the installer's own artifact.
$OURS = @("uninstall-infiny.bat")
if (Test-Path $InstallDir) {
    $busy = Get-ChildItem -LiteralPath $InstallDir -Force -ErrorAction SilentlyContinue |
            Where-Object { $OURS -notcontains $_.Name }
    if ($busy) {
        Write-Err "$InstallDir is not empty ($($busy.Count) item(s))."
        Write-Host "  Uninstalling Infiny removes its install directory, so anything" -ForegroundColor Yellow
        Write-Host "  else in there would be deleted with it." -ForegroundColor Yellow
        Write-Host "  Choose an empty or non-existent directory." -ForegroundColor Yellow
        Pause-Exit 1
    }
}

# --- Step 4: install ---------------------------------------------------------

Write-Step "Unpacking Infiny Box (a minute or two)..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
wsl --import $DistroName $InstallDir $WslFile
if ($LASTEXITCODE -ne 0) {
    Write-Err "Install failed (exit code $LASTEXITCODE)."
    Pause-Exit 1
}
Write-Ok "Infiny Box installed to $InstallDir"

# --- Step 4: shortcut --------------------------------------------------------
Write-Step "Creating the shortcut..."

# The shortcut points straight at wsl.exe and opens a VISIBLE terminal window.
# It used to go through a launcher.vbs with `objShell.Run ..., 0, False` - the
# zero means hidden window. That was left over from when the client was a
# browser UI: the process hid itself and the browser showed up instead. For the
# Box, where the terminal IS the client, that shortcut starts an invisible
# process and the user sees nothing at all.
$iconPath = Join-Path $PSScriptRoot "infiny.ico"
if (-not (Test-Path $iconPath)) { $iconPath = "$env:SystemRoot\System32\shell32.dll,43" }

$WshShell = New-Object -ComObject WScript.Shell
foreach ($dest in @(
    "$env:USERPROFILE\Desktop\Infiny Box.lnk",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Infiny Box.lnk"
)) {
    $s = $WshShell.CreateShortcut($dest)
    $s.TargetPath       = "$env:SystemRoot\System32\wsl.exe"
    $s.Arguments        = "-d $DistroName -u root -- infiny"
    $s.IconLocation     = $iconPath
    $s.Description      = "Infiny Box - an AI terminal, sandboxed"
    $s.WorkingDirectory = "$env:USERPROFILE"
    $s.Save()
}
Write-Ok "Shortcut 'Infiny Box' created on the Desktop and in the Start menu."

# --- Uninstaller -------------------------------------------------------------
# The uninstaller used to live only in the folder the installer was run from.
# Delete that folder - which people do, it is usually Downloads - and there was
# no supported way left to remove the product: no entry in Add/Remove Programs,
# nothing in the Start menu, just a 2 GB distro and two shortcuts.
#
# Copy it next to the install and register it with Windows, so uninstalling
# works the way people expect regardless of where the installer came from.
$uninstallSrc = Join-Path $PSScriptRoot "uninstall-infiny.bat"
if (Test-Path $uninstallSrc) {
    Copy-Item -LiteralPath $uninstallSrc -Destination $InstallDir -Force
    $uninstallDst = Join-Path $InstallDir "uninstall-infiny.bat"

    # HKCU, not HKLM: the whole installer runs without administrator rights
    # (WSL aside), and writing a machine-wide entry would need them.
    $regKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\InfinyBox"
    New-Item -Path $regKey -Force | Out-Null
    Set-ItemProperty -Path $regKey -Name "DisplayName"     -Value "Infiny Box"
    Set-ItemProperty -Path $regKey -Name "DisplayIcon"     -Value $iconPath
    Set-ItemProperty -Path $regKey -Name "Publisher"       -Value "sheffjr"
    Set-ItemProperty -Path $regKey -Name "InstallLocation" -Value $InstallDir
    Set-ItemProperty -Path $regKey -Name "UninstallString" -Value "`"$uninstallDst`""
    Set-ItemProperty -Path $regKey -Name "NoModify"        -Value 1 -Type DWord
    Set-ItemProperty -Path $regKey -Name "NoRepair"        -Value 1 -Type DWord

    Write-Ok "Uninstaller registered - 'Infiny Box' appears in Add/Remove Programs."
} else {
    Write-Host "  Note: uninstall-infiny.bat was not next to the installer," -ForegroundColor Yellow
    Write-Host "  so no uninstall entry was created." -ForegroundColor Yellow
}

# --- Done --------------------------------------------------------------------
Write-Host ""
Write-Host "  +==========================================+" -ForegroundColor Green
Write-Host "  |             Installation done             |" -ForegroundColor Green
Write-Host "  +==========================================+" -ForegroundColor Green
Write-Host ""
Write-Host "  Double-click the 'Infiny Box' shortcut to start." -ForegroundColor White
Write-Host ""
Write-Host "  On first run the Box asks which model to connect to." -ForegroundColor White
Write-Host "  There is NO model inside - you need your own server running:" -ForegroundColor White
Write-Host "    Ollama, LM Studio, llama.cpp, vLLM, or a cloud endpoint." -ForegroundColor Gray
Write-Host ""
Write-Host "  IMPORTANT: that server must listen on 0.0.0.0, not 127.0.0.1," -ForegroundColor Yellow
Write-Host "  or the sandbox cannot see it. For Ollama that means setting" -ForegroundColor Yellow
Write-Host "  OLLAMA_HOST=0.0.0.0 and restarting it." -ForegroundColor Yellow
Write-Host ""
if (-not $NoPause) { Read-Host "Press Enter to exit" }
