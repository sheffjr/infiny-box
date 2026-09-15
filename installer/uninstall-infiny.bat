@echo off
setlocal
:: Infiny Box - uninstaller.
:: ASCII ONLY - see the note in install-infiny.bat about cmd.exe codepages.

echo Removing Infiny Box...

:: Find OUR install directory, and only ours.
::
:: The previous version walked every Lxss entry and took the one whose BasePath
:: contained the substring "Infiny". That matches far too much: a completely
:: unrelated distro living in, say, D:\Infiny-tools\Ubuntu would match, and the
:: script would then delete that distro's ext4.vhdx - somebody else's machine,
:: gone, from an uninstaller for a different product.
::
:: Match on the distro NAME instead, which is exact. PowerShell does the lookup
:: because reading a specific value out of a specific subkey is painful in cmd,
:: and getting it subtly wrong is how the previous bug happened.
set "BASEPATH="
for /f "usebackq delims=" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' |" ^
  "ForEach-Object { $p = Get-ItemProperty $_.PSPath;" ^
  "  if ($p.DistributionName -eq 'Infiny') { $p.BasePath } } | Select-Object -First 1"`) do set "BASEPATH=%%p"

:: WSL stores some paths with a \\?\ prefix, which del and rmdir do not parse.
:: Strip it if present - otherwise the delete fails silently (2>nul) and leaves
:: about 2 GB behind, which is exactly what this lookup exists to prevent.
if defined BASEPATH (
    set "BASEPATH=%BASEPATH:\\?\=%"
)

:: --unregister deletes the virtual disk itself. The explicit delete below is a
:: fallback for installs left half-removed by earlier versions.
wsl --unregister Infiny

del "%USERPROFILE%\Desktop\Infiny Box.lnk" 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Infiny Box.lnk" 2>nul
:: older shortcut names, in case an earlier version installed them
del "%USERPROFILE%\Desktop\Infiny.lnk" 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Infiny.lnk" 2>nul

:: Remove the Add/Remove Programs entry the installer created.
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\InfinyBox" /f >nul 2>nul

:: Delete only the virtual disk, never the whole folder. An earlier version ran
:: `rmdir /s /q` on the install directory - if anything else happened to live
:: there, it went too. The installer now refuses non-empty targets, but old
:: installs may predate that check.
:: Note we do NOT delete this script, even though the installer copies it here.
:: A running .bat cannot delete itself - cmd.exe reads it line by line as it
:: executes, and pulling the file out from under it breaks the run. The usual
:: `(goto) 2>nul & del "%~f0"` trick works but is fragile enough that leaving
:: one 2 KB file behind is the better trade.
if defined BASEPATH (
    del "%BASEPATH%\ext4.vhdx" 2>nul
    rmdir "%BASEPATH%" 2>nul
    if exist "%BASEPATH%" (
        echo   Left behind: %BASEPATH%
        echo   It holds only this uninstaller - delete the folder when you close this window.
    )
) else (
    echo   Could not find the install directory in the registry.
    echo   If anything is left over, delete it by hand.
)

echo Done. Infiny Box removed.
pause
