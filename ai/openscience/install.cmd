@echo off
rem OS-CXCL11 verified kit. Example: install.cmd -VerifyOnly
rem Offline test: install.cmd -OfflineProfileRoot D:\temp\os-kit-test
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_kit.ps1" %*
set "KIT_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %KIT_EXIT%
