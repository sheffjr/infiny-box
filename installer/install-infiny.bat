@echo off
setlocal
:: Infiny Box - installer launcher.
::
:: ASCII ONLY - do not put Cyrillic (or any non-ASCII) text in this file.
:: cmd.exe reads .bat in the console OEM codepage (866 for Russian Windows),
:: while editors save UTF-8. The mismatch mangles the bytes, and fragments of
:: broken lines get executed as commands:
::     '-NoProfile' is not recognized as an internal or external command
:: All localized text lives in install-infiny.ps1, which is UTF-8 with BOM and
:: is read correctly by PowerShell.
::
:: Admin rights are NOT requested here. `wsl --import` works as a normal user;
:: elevation is only needed to enable the WSL2 platform for the first time, and
:: the PowerShell script says so explicitly if that case comes up.

if not exist "%~dp0install-infiny.ps1" (
    echo [ERROR] install-infiny.ps1 not found next to this file.
    echo Extract the whole installer folder, not a single file.
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0infiny.wsl" (
    echo [ERROR] infiny.wsl not found next to this file.
    echo install-infiny.bat and infiny.wsl must sit in the same folder.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-infiny.ps1"
set "RC=%errorlevel%"

:: pause is mandatory. Without it the window closes together with the process
:: and any error stays invisible - the user sees only a flash.
if not "%RC%"=="0" (
    echo.
    echo Installer exited with code %RC%. See the message above.
)
echo.
pause
