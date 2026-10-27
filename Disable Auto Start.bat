@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APPDIR=%~dp0"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Library Manager Server.lnk"

echo ==============================================
echo    Library Manager - Disable Auto Start
echo ==============================================
echo.
echo This switches OFF automatic startup and stops the background
echo server right now. The link will stop working until you start the
echo app again with "Start Library Manager.bat".
echo.

rem --- remove the shortcut from the Windows Startup folder -------------
if exist "%LNK%" goto :remove_it
echo Auto start was not enabled - no shortcut found, nothing to remove.
goto :removed

:remove_it
del /q "%LNK%"
echo Auto start is now OFF - the app will not start with Windows any more.

:removed
echo.

rem --- stop the background server and its supervisor -------------------
echo Stopping the background server if it is running...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and (($_.CommandLine -like ('*' + $env:APPDIR + '*')) -or ($_.CommandLine -like '*server_watchdog.pyw*')) } | ForEach-Object { Write-Output ('Stopping ' + $_.Name + ' PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo.
echo Done. To use the app again later, double-click
echo "Start Library Manager.bat".
echo.
pause
exit /b 0
